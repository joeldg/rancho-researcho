"""Controlled queue-dispatch tests for the asynchronous research boundary."""

import uuid

import pytest

from rancho.queue import QueueUnavailableError, enqueue_research_task


class _FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, str]] = []

    async def enqueue_job(self, name: str, task_id: str) -> None:
        self.jobs.append((name, task_id))


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_enqueue_dispatches_committed_task() -> None:
    task_id = uuid.uuid4()
    queue = _FakeQueue()

    async def factory(settings):
        return queue

    import asyncio

    asyncio.run(enqueue_research_task(task_id, "redis://localhost:6379/0", factory))
    assert queue.jobs == [("run_research_task", str(task_id))]


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_enqueue_requires_configured_redis() -> None:
    import asyncio

    with pytest.raises(QueueUnavailableError):
        asyncio.run(enqueue_research_task(uuid.uuid4(), None))
