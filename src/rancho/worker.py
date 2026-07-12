"""Bounded arq worker for Phase 2 research-task evidence collection."""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from arq.connections import RedisSettings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rancho.config import Settings, get_settings
from rancho.db import create_engine, create_session_factory
from rancho.db_models import EventType, Evidence, ResearchTask, TaskEvent, TaskStatus
from rancho.extract import ContentUnavailableError, WebContentFetcher
from rancho.llm import get_local_llm_client
from rancho.planning import plan_queries
from rancho.search import (
    OrchestratedSearch,
    ProviderUnavailableError,
    SearchOrchestrator,
    _build_active_adapters,
)


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
async def run_research_task(ctx: dict[str, Any], task_id: str) -> None:
    """Collect bounded, safely fetched evidence for one queued research task.

    The worker intentionally finishes ``partial``: LLM planning, claim extraction,
    and final synthesis remain separate future slices. It never creates evidence
    for an unavailable or refused fetch.
    """
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
        queries = [task.objective]
        if settings.research_planning:
            llm = ctx.get("llm") or get_local_llm_client(settings)
            if llm is None:
                await _finish_partial(factory, task.id)
                return
            queries = await asyncio.to_thread(
                plan_queries,
                llm,
                task.objective,
                settings.research_max_iterations,
                settings.research_max_planner_tokens,
            )
            if not queries:
                await _finish_partial(factory, task.id)
                return
        fetcher = ctx.get("fetcher") or WebContentFetcher()
        started = time.monotonic()
        seen_urls: set[str] = set()
        remaining = task.budget_max_sources
        for iteration, query in enumerate(queries, start=1):
            if time.monotonic() - started >= settings.research_max_elapsed_seconds:
                break
            if await _is_cancel_requested(factory, task.id):
                await _finish_cancelled(factory, task.id)
                return
            await _record_progress(factory, task.id, iteration)
            outcome = await _search_once(search, query, remaining)
            await _record_search_outcome(factory, task.id, outcome)
            for result in outcome.results:
                url = str(result.url)
                if url in seen_urls or remaining <= 0:
                    continue
                seen_urls.add(url)
                if await _is_cancel_requested(factory, task.id):
                    await _finish_cancelled(factory, task.id)
                    return
                await _collect_evidence(factory, task.id, result, fetcher)
                remaining -= 1
            if remaining <= 0:
                break

        await _finish_partial(factory, task.id)
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
) -> None:
    """Safely fetch one result and persist evidence only after success."""
    try:
        page = await asyncio.to_thread(fetcher.fetch, str(result.url))
    except ContentUnavailableError:
        await _record_fetch_skip(factory, task_id, result.source_id)
        return

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


async def _finish_partial(factory: async_sessionmaker, task_id: UUID) -> None:
    """Record the honest terminal state until approved synthesis exists."""
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
            {"reason": "synthesis_not_implemented"},
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


class WorkerSettings:
    """arq entry point for the trusted Redis-backed worker."""

    functions = [run_research_task]
    redis_settings = RedisSettings.from_dsn(
        get_settings().redis_url or "redis://localhost:6379/0"
    )
