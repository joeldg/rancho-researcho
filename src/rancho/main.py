"""FastAPI entry point for Rancho Researcho."""

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from rancho.config import Settings, get_settings
from rancho.db import get_session_factory
from rancho.db_models import TERMINAL_STATES, Evidence, ResearchTask, TaskEvent
from rancho.enrich import SnippetEnricher
from rancho.extract import WebContentFetcher
from rancho.llm import get_local_llm_client
from rancho.models import (
    ErrorResponse,
    ResearchRequest,
    ResearchTaskAccepted,
    ResearchTaskState,
    SearchRequest,
    SearchResponse,
)
from rancho.queue import QueueUnavailableError, enqueue_research_task
from rancho.research import ResearchConflictError, create_or_get_research_task
from rancho.search import (
    ProviderUnavailableError,
    SearchAdapter,
    SearchOrchestrator,
    get_search_adapter,
)


def _error(code: str, message: str, request_id: str) -> dict:
    return ErrorResponse(
        error={"code": code, "message": message}, request_id=request_id
    ).model_dump(mode="json")


def _status_url(settings: Settings, task_id: UUID) -> str:
    base = str(settings.public_base_url).rstrip("/") if settings.public_base_url else ""
    return f"{base}/v1/tasks/{task_id}"


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
def get_snippet_enricher(
    settings: Settings = Depends(get_settings),
) -> SnippetEnricher | None:
    """Build the snippet enricher only when enrichment is enabled and possible."""
    if not settings.enrich_is_enabled:
        return None
    llm = get_local_llm_client(settings)
    if llm is None:
        return None
    return SnippetEnricher(
        llm, WebContentFetcher(), settings.search_enrich_max_results
    )

app = FastAPI(
    title="Rancho Researcho",
    version="0.1.0",
    description="A self-hosted, evidence-first web research service.",
)


# @spec[RANCHO_API_SECURITY.md#http-contract]
@app.get("/health")
def health() -> dict[str, str]:
    """Return process health without exposing configuration or secrets."""
    return {"status": "ok"}


# @spec[RANCHO_API_SECURITY.md#http-contract]
@app.get("/ready")
def ready(
    settings: Settings = Depends(get_settings),
    adapter: SearchAdapter | SearchOrchestrator | None = Depends(get_search_adapter),
) -> Response:
    """Report whether a search adapter is configured for traffic."""
    if not settings.search_is_configured or adapter is None:
        return JSONResponse(
            {"status": "not_ready", "reason": "search_provider_unconfigured"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    try:
        adapter.check_ready()
    except ProviderUnavailableError:
        return JSONResponse(
            {"status": "not_ready", "reason": "search_provider_unreachable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return JSONResponse({"status": "ready"})


# @spec[RANCHO_API_SECURITY.md#http-contract]
@app.get("/metrics", response_class=PlainTextResponse)
def metrics(settings: Settings = Depends(get_settings)) -> str:
    """Expose a minimal Prometheus-compatible configuration health signal."""
    configured = int(settings.search_is_configured)
    return (
        "# HELP rancho_search_provider_configured "
        "Whether a search provider is configured.\n"
        "# TYPE rancho_search_provider_configured gauge\n"
        f"rancho_search_provider_configured {configured}\n"
    )


# @spec[RANCHO_API_SECURITY.md#http-contract]
@app.post(
    "/v1/search",
    response_model=SearchResponse,
    responses={503: {"model": ErrorResponse}},
)
@app.post(
    "/search",
    response_model=SearchResponse,
    responses={503: {"model": ErrorResponse}},
    include_in_schema=False,
)
def search(
    request: SearchRequest,
    settings: Settings = Depends(get_settings),
    adapter: SearchAdapter | SearchOrchestrator | None = Depends(get_search_adapter),
    enricher: SnippetEnricher | None = Depends(get_snippet_enricher),
) -> SearchResponse | JSONResponse:
    """Serve a bounded search request or an explicit unavailable-provider error.

    A configured adapter is intentionally required before this endpoint returns
    results. The Phase 1 scaffold never fabricates search results or citations.
    """
    request_id = f"req_{uuid4().hex}"
    if not settings.search_is_configured or adapter is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error={
                    "code": "provider_unavailable",
                    "message": "No search provider is configured.",
                },
                request_id=request_id,
            ).model_dump(mode="json"),
        )

    try:
        if isinstance(adapter, SearchOrchestrator):
            outcome = adapter.run(request.query, request.max_results)
            results, warnings = outcome.results, outcome.warnings
        else:
            results = adapter.search(request.query, request.max_results)
            warnings = []
    except ProviderUnavailableError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error={
                    "code": "provider_unavailable",
                    "message": "The configured search provider is unavailable.",
                },
                request_id=request_id,
            ).model_dump(mode="json"),
        )
    if enricher is not None:
        results, warnings = enricher.enrich(request.query, results, warnings)
    return SearchResponse(results=results, request_id=request_id, warnings=warnings)


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
@app.post(
    "/v1/research",
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def create_research(
    request: ResearchRequest,
    settings: Settings = Depends(get_settings),
    session_factory: async_sessionmaker | None = Depends(get_session_factory),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Create a queued research task and its task.created event, then enqueue it."""
    request_id = f"req_{uuid4().hex}"
    if session_factory is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_error(
                "database_unavailable", "No durable store is configured.", request_id
            ),
        )
    async with session_factory() as session:
        try:
            task, _created = await create_or_get_research_task(
                session, request.objective, request.max_sources, idempotency_key
            )
        except ResearchConflictError:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=_error(
                    "idempotency_key_conflict",
                    "The idempotency key was reused with a different request.",
                    request_id,
                ),
            )
        task_id, task_status = task.id, task.status.value
    # Enqueue only after the creation transaction has committed.
    try:
        await enqueue_research_task(task_id, settings.redis_url)
    except QueueUnavailableError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_error(
                "queue_unavailable",
                "The task was stored but could not be dispatched.",
                request_id,
            ),
        )
    status_url = _status_url(settings, task_id)
    body = ResearchTaskAccepted(
        task_id=str(task_id), status=task_status, status_url=status_url
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=body.model_dump(),
        headers={"Location": status_url},
    )


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
@app.get(
    "/v1/tasks/{task_id}",
    response_model=ResearchTaskState,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def get_task(
    task_id: UUID,
    session_factory: async_sessionmaker | None = Depends(get_session_factory),
) -> ResearchTaskState | JSONResponse:
    """Return the current durable state of a research task."""
    request_id = f"req_{uuid4().hex}"
    if session_factory is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_error(
                "database_unavailable", "No durable store is configured.", request_id
            ),
        )
    async with session_factory() as session:
        task = await session.get(ResearchTask, task_id)
        if task is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=_error("task_not_found", "No such task.", request_id),
            )
        count_result = await session.execute(
            select(func.count())
            .select_from(Evidence)
            .where(Evidence.task_id == task.id)
        )
        return ResearchTaskState(
            task_id=str(task.id),
            status=task.status.value,
            attempt=task.attempt,
            evidence_count=int(count_result.scalar_one()),
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


# @spec[RANCHO_ASYNC_RESEARCH.md#sse-and-events]
@app.get(
    "/v1/tasks/{task_id}/events",
    response_model=None,
    responses={
        404: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def stream_task_events(
    task_id: UUID,
    session_factory: async_sessionmaker | None = Depends(get_session_factory),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse | JSONResponse:
    """Replay durable task events and poll until the task reaches a terminal state."""
    request_id = f"req_{uuid4().hex}"
    if session_factory is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_error(
                "database_unavailable", "No durable store is configured.", request_id
            ),
        )
    after_sequence = _parse_last_event_id(last_event_id)
    if after_sequence is None:
        return JSONResponse(
            status_code=status.HTTP_410_GONE,
            content=_error(
                "event_history_expired",
                "The requested event history is unavailable.",
                request_id,
            ),
        )
    async with session_factory() as session:
        task = await session.get(ResearchTask, task_id)
        if task is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=_error("task_not_found", "No such task.", request_id),
            )
        if not await _is_replay_point_available(session, task_id, after_sequence):
            return JSONResponse(
                status_code=status.HTTP_410_GONE,
                content=_error(
                    "event_history_expired",
                    "The requested event history is unavailable.",
                    request_id,
                ),
            )
    return StreamingResponse(
        _event_stream(session_factory, task_id, after_sequence),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _parse_last_event_id(value: str | None) -> int | None:
    """Parse a non-negative durable event sequence or return an invalid marker."""
    if value is None:
        return 0
    try:
        sequence = int(value)
    except ValueError:
        return None
    return sequence if sequence >= 0 else None


async def _is_replay_point_available(
    session, task_id: UUID, after_sequence: int
) -> bool:
    """Require an explicit retained event for nonzero replay positions."""
    if after_sequence == 0:
        return True
    result = await session.execute(
        select(TaskEvent.id).where(
            TaskEvent.task_id == task_id, TaskEvent.sequence == after_sequence
        )
    )
    return result.scalar_one_or_none() is not None


async def _event_stream(
    session_factory: async_sessionmaker, task_id: UUID, after_sequence: int
) -> AsyncIterator[str]:
    """Yield ordered durable events after one sequence, then close at terminal state."""
    sequence = after_sequence
    while True:
        async with session_factory() as session:
            result = await session.execute(
                select(TaskEvent)
                .where(TaskEvent.task_id == task_id, TaskEvent.sequence > sequence)
                .order_by(TaskEvent.sequence)
            )
            events = result.scalars().all()
            task = await session.get(ResearchTask, task_id)
        for event in events:
            sequence = event.sequence
            yield _format_sse_event(event)
        if task is None or task.status in TERMINAL_STATES:
            return
        await asyncio.sleep(0.2)


def _format_sse_event(event: TaskEvent) -> str:
    """Encode one redacted durable event using the SSE wire format."""
    payload = {
        "task_id": str(event.task_id),
        "sequence": event.sequence,
        "timestamp": event.created_at.isoformat(),
        "stage": event.stage,
        "data": event.payload,
    }
    data = json.dumps(payload, separators=(",", ":"), default=str)
    return f"id: {event.sequence}\nevent: {event.type.value}\ndata: {data}\n\n"
