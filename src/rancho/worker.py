"""Bounded arq worker for Phase 2 research-task lifecycle transitions."""

from __future__ import annotations

from uuid import UUID

from arq.connections import RedisSettings
from sqlalchemy import func, select

from rancho.config import get_settings
from rancho.db import create_engine, create_session_factory
from rancho.db_models import EventType, ResearchTask, TaskEvent, TaskStatus


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
async def run_research_task(ctx: dict, task_id: str) -> None:
    """Claim one queued task and finish the current bounded placeholder stage."""
    settings = get_settings()
    engine = create_engine(settings)
    if engine is None:
        return
    factory = create_session_factory(engine)
    async with factory() as session:
        task = await session.get(ResearchTask, UUID(task_id), with_for_update=True)
        if task is None or task.status is not TaskStatus.queued:
            return
        task.status = TaskStatus.running
        await _append_event(session, task.id, EventType.stage_started, "research")
        # The deep-research loop is deliberately not implemented in this slice.
        task.status = TaskStatus.partial
        await _append_event(session, task.id, EventType.task_partial, "research")
        await session.commit()
    await engine.dispose()


async def _append_event(
    session, task_id: UUID, event_type: EventType, stage: str
) -> None:
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
            payload={},
        )
    )


class WorkerSettings:
    """arq entry point for the trusted Redis-backed worker."""

    functions = [run_research_task]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379/0")
