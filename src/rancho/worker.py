"""Bounded arq worker for Phase 2 research-task evidence collection."""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rancho.config import Settings, get_settings
from rancho.db import create_engine, create_session_factory
from rancho.db_models import (
    Candidate,
    Claim,
    EventType,
    Evidence,
    ResearchTask,
    TaskEvent,
    TaskStatus,
)
from rancho.evaluation import EvaluationUnavailableError, evaluate_evidence
from rancho.extract import ContentUnavailableError, WebContentFetcher
from rancho.findall import FindAllUnavailableError, extract_candidates
from rancho.llm import get_local_llm_client
from rancho.monitors import finalize_monitor_task, launch_due_monitors
from rancho.planning import plan_queries
from rancho.search import (
    OrchestratedSearch,
    ProviderUnavailableError,
    SearchOrchestrator,
    _build_active_adapters,
)
from rancho.synthesis import (
    VerificationUnavailableError,
    render_verified_claims,
    synthesize_claims,
)


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
async def run_research_task(ctx: dict[str, Any], task_id: str) -> None:
    """Collect evidence, verify candidate claims, then finish honestly."""
    settings = ctx.get("settings") or get_settings()
    factory, engine = _session_factory(ctx, settings)
    if factory is None:
        return
    try:
        task = await _claim_task(factory, UUID(task_id))
        if task is None:
            return
        if task.status is TaskStatus.cancel_requested:
            await _finish_cancelled(factory, task.id)
            return

        search = ctx.get("search") or _configured_search(settings)
        llm = ctx.get("llm") or get_local_llm_client(settings)
        model_tokens_remaining = settings.research_max_model_tokens
        queries = [task.objective]
        if settings.research_planning or task.task_type == "findall":
            if llm is None:
                await _finish_partial(factory, task.id, "model_unavailable")
                return
            if await _cancel_at_boundary(factory, task.id):
                return
            if model_tokens_remaining < settings.research_max_planner_tokens:
                await _finish_partial(factory, task.id, "model_budget_exhausted")
                return
            model_tokens_remaining -= settings.research_max_planner_tokens
            queries = await asyncio.to_thread(
                plan_queries,
                llm,
                task.objective,
                settings.research_max_iterations,
                settings.research_max_planner_tokens,
            )
            if await _cancel_at_boundary(factory, task.id):
                return
            if not queries:
                await _finish_partial(factory, task.id, "planning_unavailable")
                return
        fetcher = ctx.get("fetcher") or WebContentFetcher()
        started = time.monotonic()
        seen_urls: set[str] = set()
        remaining = task.budget_max_sources
        iteration = 0
        research_incomplete = False
        while queries and iteration < settings.research_max_iterations:
            if time.monotonic() - started >= settings.research_max_elapsed_seconds:
                research_incomplete = True
                break
            if await _cancel_at_boundary(factory, task.id):
                return
            iteration += 1
            query = queries.pop(0)
            await _record_progress(factory, task.id, iteration)
            outcome = await _search_once(search, query, remaining)
            if await _cancel_at_boundary(factory, task.id):
                return
            await _record_search_outcome(factory, task.id, outcome)
            research_incomplete = research_incomplete or bool(outcome.warnings)
            for result in outcome.results:
                url = str(result.url)
                if url in seen_urls or remaining <= 0:
                    continue
                seen_urls.add(url)
                if await _cancel_at_boundary(factory, task.id):
                    return
                canonical_url = await _collect_evidence(
                    factory, task.id, result, fetcher
                )
                remaining -= 1
                if canonical_url:
                    seen_urls.add(canonical_url)
                if await _cancel_at_boundary(factory, task.id):
                    return
            if remaining <= 0:
                break
            remaining_iterations = settings.research_max_iterations - iteration
            if llm is not None and remaining_iterations > 0:
                if await _cancel_at_boundary(factory, task.id):
                    return
                evidence = await _task_evidence(factory, task.id)
                if model_tokens_remaining < settings.research_max_planner_tokens:
                    await _finish_partial(factory, task.id, "model_budget_exhausted")
                    return
                model_tokens_remaining -= settings.research_max_planner_tokens
                try:
                    evaluation = await asyncio.to_thread(
                        evaluate_evidence,
                        llm,
                        task.objective,
                        evidence,
                        remaining_iterations,
                        settings.research_max_planner_tokens,
                    )
                except EvaluationUnavailableError:
                    await _finish_partial(factory, task.id, "evaluation_unavailable")
                    return
                if await _cancel_at_boundary(factory, task.id):
                    return
                if evaluation.complete:
                    queries.clear()
                else:
                    queued = set(queries)
                    secondary = [
                        query for query in evaluation.queries if query not in queued
                    ]
                    queries[0:0] = secondary

        if research_incomplete:
            await _finish_partial(factory, task.id, "research_incomplete")
            return
        if llm is None:
            await _finish_partial(factory, task.id, "verification_unavailable")
            return
        synthesis_tokens = min(
            settings.research_max_planner_tokens * 4,
            model_tokens_remaining,
            2048,
        )
        if synthesis_tokens < 1:
            await _finish_partial(factory, task.id, "model_budget_exhausted")
            return
        if task.task_type == "findall":
            await _extract_findall_and_finish(
                factory,
                task.id,
                llm,
                task.output_schema or {},
                synthesis_tokens,
            )
            await finalize_monitor_task(factory, task.id)
            return
        await _verify_and_finish(factory, task.id, llm, synthesis_tokens)
    finally:
        if engine is not None:
            await engine.dispose()


def _session_factory(
    ctx: dict[str, Any], settings: Settings
) -> tuple[async_sessionmaker | None, Any | None]:
    """Use injected test resources or construct the worker's durable session."""
    if factory := ctx.get("session_factory"):
        return factory, None
    engine = create_engine(settings)
    if engine is None:
        return None, None
    return create_session_factory(engine), engine


def _configured_search(settings: Settings) -> SearchOrchestrator | None:
    """Build the operator-configured, trusted search boundary for the worker."""
    adapters = _build_active_adapters(settings)
    return SearchOrchestrator(adapters) if adapters else None


async def _claim_task(
    factory: async_sessionmaker, task_id: UUID
) -> ResearchTask | None:
    """Durably claim one queued task before performing external work."""
    async with factory() as session:
        task = await session.get(ResearchTask, task_id, with_for_update=True)
        if task is None or task.status not in {
            TaskStatus.queued,
            TaskStatus.cancel_requested,
        }:
            return None
        if task.status is TaskStatus.cancel_requested:
            return task
        task.status = TaskStatus.running
        await _append_event(session, task.id, EventType.stage_started, "search")
        await session.commit()
        return task


async def _search_once(
    search: SearchOrchestrator | Any | None, objective: str, budget: int
) -> OrchestratedSearch:
    """Run exactly one bounded search pass without blocking the arq event loop."""
    if search is None:
        return OrchestratedSearch(results=[], warnings=["Search is unavailable."])
    try:
        return await asyncio.to_thread(search.run, objective, budget)
    except ProviderUnavailableError:
        return OrchestratedSearch(results=[], warnings=["Search is unavailable."])


async def _record_search_outcome(
    factory: async_sessionmaker, task_id: UUID, outcome: OrchestratedSearch
) -> None:
    """Persist a redacted search summary before fetching individual results."""
    async with factory() as session:
        await _append_event(
            session,
            task_id,
            EventType.search_completed,
            "search",
            {"result_count": len(outcome.results), "degraded": bool(outcome.warnings)},
        )
        await session.commit()


async def _record_progress(
    factory: async_sessionmaker, task_id: UUID, iteration: int
) -> None:
    """Persist a redacted bounded-loop progress marker."""
    async with factory() as session:
        await _append_event(
            session, task_id, EventType.progress, "research", {"iteration": iteration}
        )
        await session.commit()


async def _collect_evidence(
    factory: async_sessionmaker,
    task_id: UUID,
    result: Any,
    fetcher: WebContentFetcher | Any,
) -> str | None:
    """Safely fetch one result and persist evidence only after success."""
    try:
        page = await asyncio.to_thread(fetcher.fetch, str(result.url))
    except ContentUnavailableError:
        await _record_fetch_skip(factory, task_id, result.source_id)
        return None

    content = page.markdown
    async with factory() as session:
        session.add(
            Evidence(
                task_id=task_id,
                canonical_url=page.final_url,
                original_url=str(result.url),
                title=result.title,
                content=content,
                content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                retrieved_at=datetime.now(timezone.utc),
                source_meta={"source_id": result.source_id},
            )
        )
        await _append_event(
            session,
            task_id,
            EventType.evidence_extracted,
            "evidence",
            {"source_id": result.source_id, "outcome": "stored"},
        )
        await session.commit()
    return page.final_url


async def _record_fetch_skip(
    factory: async_sessionmaker, task_id: UUID, source_id: str
) -> None:
    """Record a redacted unavailable evidence outcome without storing a page."""
    async with factory() as session:
        await _append_event(
            session,
            task_id,
            EventType.evidence_extracted,
            "evidence",
            {"source_id": source_id, "outcome": "unavailable"},
        )
        await session.commit()


async def _is_cancel_requested(factory: async_sessionmaker, task_id: UUID) -> bool:
    """Check durable cancellation between bounded fetch stages."""
    async with factory() as session:
        task = await session.get(ResearchTask, task_id)
        return task is not None and task.status is TaskStatus.cancel_requested


async def _cancel_at_boundary(factory: async_sessionmaker, task_id: UUID) -> bool:
    """Finish cancellation before or after an external/model stage."""
    if not await _is_cancel_requested(factory, task_id):
        return False
    await _finish_cancelled(factory, task_id)
    return True


async def _task_evidence(factory: async_sessionmaker, task_id: UUID) -> list[Evidence]:
    """Load only retained evidence owned by one task for model evaluation."""
    async with factory() as session:
        return list(
            (
                await session.execute(
                    select(Evidence)
                    .where(Evidence.task_id == task_id)
                    .order_by(Evidence.id)
                )
            )
            .scalars()
            .all()
        )


async def _finish_partial(
    factory: async_sessionmaker, task_id: UUID, reason: str = "verification_incomplete"
) -> None:
    """Record a redacted partial outcome when verification cannot complete."""
    async with factory() as session:
        task = await session.get(ResearchTask, task_id, with_for_update=True)
        if task is None or task.status is not TaskStatus.running:
            return
        task.status = TaskStatus.partial
        await _append_event(
            session,
            task.id,
            EventType.task_partial,
            "synthesis",
            {"reason": reason},
        )
        await session.commit()


# @spec[RANCHO_CLAIM_VERIFICATION.md#requirements]
async def _verify_and_finish(
    factory: async_sessionmaker,
    task_id: UUID,
    llm: Any,
    max_output_tokens: int,
) -> None:
    """Persist only verified claims and complete atomically after verification."""
    if await _cancel_at_boundary(factory, task_id):
        return
    evidence = await _task_evidence(factory, task_id)
    async with factory() as session:
        task = await session.get(ResearchTask, task_id)
        if task is None:
            return
        objective = task.objective
    try:
        verified = await asyncio.to_thread(
            synthesize_claims,
            llm,
            objective,
            list(evidence),
            max_output_tokens,
        )
    except VerificationUnavailableError:
        await _finish_partial(factory, task_id, "verification_unavailable")
        return
    if await _cancel_at_boundary(factory, task_id):
        return
    if not verified:
        await _finish_partial(factory, task_id, "no_verified_claims")
        return

    result = render_verified_claims(verified)
    async with factory() as session:
        task = await session.get(ResearchTask, task_id, with_for_update=True)
        if task is None or task.status is not TaskStatus.running:
            return
        for item in verified:
            claim = Claim(task_id=task_id, text=item.text, evidence=list(item.evidence))
            session.add(claim)
            await session.flush()
            await _append_event(
                session,
                task_id,
                EventType.claim_verified,
                "verification",
                {"claim_id": str(claim.id), "evidence_count": len(item.evidence)},
            )
        task.final_result = result
        task.status = TaskStatus.completed
        await _append_event(session, task_id, EventType.task_completed, "synthesis")
        await session.commit()


# @spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
async def _extract_findall_and_finish(
    factory: async_sessionmaker,
    task_id: UUID,
    llm: Any,
    output_schema: dict[str, str],
    max_output_tokens: int,
) -> None:
    """Persist only schema-valid candidates linked to task-owned evidence."""
    if await _cancel_at_boundary(factory, task_id):
        return
    evidence = await _task_evidence(factory, task_id)
    async with factory() as session:
        task = await session.get(ResearchTask, task_id)
        if task is None:
            return
        objective = task.objective
    try:
        verified = await asyncio.to_thread(
            extract_candidates,
            llm,
            objective,
            output_schema,
            evidence,
            max_output_tokens,
        )
    except FindAllUnavailableError:
        await _finish_partial(factory, task_id, "candidate_extraction_unavailable")
        return
    if await _cancel_at_boundary(factory, task_id):
        return
    if not verified:
        await _finish_partial(factory, task_id, "no_verified_candidates")
        return
    async with factory() as session:
        task = await session.get(ResearchTask, task_id, with_for_update=True)
        if task is None or task.status is not TaskStatus.running:
            return
        for item in verified:
            session.add(
                Candidate(
                    task_id=task_id,
                    data=item.data,
                    match_status="matched",
                    reasoning=item.reasoning,
                    evidence=list(item.evidence),
                )
            )
        task.status = TaskStatus.completed
        await _append_event(
            session,
            task_id,
            EventType.task_completed,
            "findall",
            {"candidate_count": len(verified)},
        )
        await session.commit()


async def _finish_cancelled(factory: async_sessionmaker, task_id: UUID) -> None:
    """Finish a requested cancellation without deleting retained evidence."""
    async with factory() as session:
        task = await session.get(ResearchTask, task_id, with_for_update=True)
        if task is None or task.status is not TaskStatus.cancel_requested:
            return
        task.status = TaskStatus.cancelled
        await _append_event(session, task.id, EventType.task_cancelled, "research")
        await session.commit()


async def _append_event(
    session: AsyncSession,
    task_id: UUID,
    event_type: EventType,
    stage: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append the next durable, monotonic event for one task."""
    result = await session.execute(
        select(func.coalesce(func.max(TaskEvent.sequence), 0)).where(
            TaskEvent.task_id == task_id
        )
    )
    session.add(
        TaskEvent(
            task_id=task_id,
            sequence=int(result.scalar_one()) + 1,
            type=event_type,
            stage=stage,
            payload=payload or {},
        )
    )


# @spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
async def run_due_monitors(ctx: dict[str, Any]) -> int:
    """Cron entry point that durably launches due monitor occurrences."""
    settings = ctx.get("settings") or get_settings()
    factory, engine = _session_factory(ctx, settings)
    if factory is None:
        return 0
    redis = ctx.get("redis")

    async def enqueue(task_id: UUID) -> None:
        if redis is not None:
            await redis.enqueue_job("run_research_task", str(task_id))

    try:
        return len(await launch_due_monitors(factory, enqueue))
    finally:
        if engine is not None:
            await engine.dispose()


class WorkerSettings:
    """arq entry point for the trusted Redis-backed worker."""

    functions = [run_research_task, run_due_monitors]
    cron_jobs = [
        cron(
            run_due_monitors,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
        )
    ]
    redis_settings = RedisSettings.from_dsn(
        get_settings().redis_url or "redis://localhost:6379/0"
    )
