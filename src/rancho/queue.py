"""Redis/arq dispatch for durable research tasks."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol

from arq.connections import RedisSettings, create_pool
from redis.exceptions import RedisError


class QueueUnavailableError(Exception):
    """Raised when a committed task cannot be handed to the worker queue."""


class _JobQueue(Protocol):
    async def enqueue_job(self, name: str, task_id: str) -> object:
        """Submit one named job to the trusted queue."""


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
async def enqueue_research_task(
    task_id: uuid.UUID,
    redis_url: str | None,
    pool_factory: Callable[[RedisSettings], Awaitable[_JobQueue]] = create_pool,
) -> None:
    """Enqueue a committed task through the configured trusted Redis service."""
    if not redis_url:
        raise QueueUnavailableError
    try:
        pool = await pool_factory(RedisSettings.from_dsn(redis_url))
        await pool.enqueue_job("run_research_task", str(task_id))
    except (OSError, RedisError) as error:
        raise QueueUnavailableError from error
