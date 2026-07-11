"""Research task creation service: bounded, idempotent, and atomic."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rancho.db_models import EventType, ResearchTask, TaskEvent, TaskStatus


class ResearchConflictError(Exception):
    """Raised when an idempotency key is reused with a different request."""


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def request_fingerprint(objective: str, max_sources: int) -> str:
    """Return a stable fingerprint of the request for idempotency checks."""
    payload = json.dumps(
        {"objective": objective, "max_sources": max_sources},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
async def create_or_get_research_task(
    session: AsyncSession,
    objective: str,
    max_sources: int,
    idempotency_key: str | None,
) -> tuple[ResearchTask, bool]:
    """Create a queued task with its task.created event in one transaction.

    Returns (task, created). An identical request replayed with the same
    idempotency key returns the original task; a different request with a
    reused key raises ResearchConflictError.
    """
    fingerprint = request_fingerprint(objective, max_sources)

    if idempotency_key:
        existing = await _find_by_key(session, idempotency_key)
        if existing is not None:
            return _reuse_or_conflict(existing, fingerprint)

    task = ResearchTask(
        objective=objective,
        budget_max_sources=max_sources,
        status=TaskStatus.queued,
        attempt=1,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
    )
    session.add(task)
    await session.flush()
    session.add(
        TaskEvent(
            task_id=task.id,
            sequence=1,
            type=EventType.task_created,
            stage="created",
            payload={"status": TaskStatus.queued.value},
        )
    )
    try:
        await session.commit()
    except IntegrityError as error:
        # A concurrent request won the same idempotency key.
        await session.rollback()
        if idempotency_key:
            existing = await _find_by_key(session, idempotency_key)
            if existing is not None:
                return _reuse_or_conflict(existing, fingerprint)
        raise ResearchConflictError from error
    return task, True


async def _find_by_key(session: AsyncSession, key: str) -> ResearchTask | None:
    result = await session.execute(
        select(ResearchTask).where(ResearchTask.idempotency_key == key)
    )
    return result.scalar_one_or_none()


def _reuse_or_conflict(
    existing: ResearchTask, fingerprint: str
) -> tuple[ResearchTask, bool]:
    if existing.request_fingerprint != fingerprint:
        raise ResearchConflictError
    return existing, False
