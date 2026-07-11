"""Background task enqueue seam.

The API enqueues a task only after its creation transaction has committed, so
the durable store is always the source of truth. The concrete arq/Redis worker
binding lands in a later sub-slice; this seam keeps the call site correct.
"""

from __future__ import annotations

import uuid


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
async def enqueue_research_task(task_id: uuid.UUID) -> None:
    """Enqueue a committed task for background execution.

    Redis/arq wiring is added in the worker sub-slice; until then this is a
    no-op so a queued task simply waits in the durable store.
    """
    return None
