"""Contract tests for the POST /v1/research and task-status endpoints."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from rancho.db import Base, get_session_factory
from rancho.db_models import ResearchTask, TaskEvent, TaskStatus
from rancho.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'api.db'}", poolclass=NullPool
    )

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def enqueue(task_id, redis_url):
        return None

    monkeypatch.setattr("rancho.main.enqueue_research_task", enqueue)
    app.dependency_overrides[get_session_factory] = lambda: factory
    try:
        with TestClient(app) as test_client:
            yield test_client, factory
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _events(factory, task_id):
    async def _query():
        async with factory() as session:
            result = await session.execute(
                select(TaskEvent).where(TaskEvent.task_id == task_id)
            )
            return result.scalars().all()

    return asyncio.run(_query())


def _task(factory, task_id):
    async def _query():
        async with factory() as session:
            return await session.get(ResearchTask, task_id)

    return asyncio.run(_query())


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_create_returns_202_with_status_and_url(client) -> None:
    test_client, _ = client
    response = test_client.post(
        "/v1/research",
        json={"objective": "study solid-state batteries", "max_sources": 5},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["task_id"]
    assert body["status_url"].endswith(f"/v1/tasks/{body['task_id']}")
    assert response.headers["location"].endswith(f"/v1/tasks/{body['task_id']}")


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_create_persists_task_and_created_event(client) -> None:
    test_client, factory = client
    response = test_client.post("/v1/research", json={"objective": "map EV startups"})
    task_id = uuid.UUID(response.json()["task_id"])

    events = _events(factory, task_id)
    assert _task(factory, task_id) is not None
    assert [(e.sequence, e.type.value) for e in events] == [(1, "task.created")]


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_rejects_empty_objective(client) -> None:
    test_client, _ = client
    assert test_client.post("/v1/research", json={"objective": ""}).status_code == 422


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_rejects_unknown_fields(client) -> None:
    test_client, _ = client
    response = test_client.post(
        "/v1/research", json={"objective": "x", "unexpected": True}
    )
    assert response.status_code == 422


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_idempotency_key_replays_same_task(client) -> None:
    test_client, factory = client
    body = {"objective": "study fuel cells", "max_sources": 7}
    headers = {"Idempotency-Key": "abc-123"}

    first = test_client.post("/v1/research", json=body, headers=headers)
    second = test_client.post("/v1/research", json=body, headers=headers)

    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["task_id"] == second.json()["task_id"]

    async def _count():
        async with factory() as session:
            result = await session.execute(select(ResearchTask))
            return len(result.scalars().all())

    assert asyncio.run(_count()) == 1


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_idempotency_key_conflict_returns_409(client) -> None:
    test_client, _ = client
    headers = {"Idempotency-Key": "dup-key"}

    test_client.post("/v1/research", json={"objective": "first"}, headers=headers)
    conflict = test_client.post(
        "/v1/research", json={"objective": "different"}, headers=headers
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_get_task_returns_state(client) -> None:
    test_client, _ = client
    task_id = test_client.post(
        "/v1/research", json={"objective": "trace supply chains"}
    ).json()["task_id"]

    response = test_client.get(f"/v1/tasks/{task_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_id
    assert body["status"] == "queued"
    assert body["attempt"] == 1


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_get_unknown_task_returns_404(client) -> None:
    test_client, _ = client
    response = test_client.get(f"/v1/tasks/{uuid.uuid4()}")
    assert response.status_code == 404


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_research_requires_configured_store() -> None:
    app.dependency_overrides[get_session_factory] = lambda: None
    try:
        with TestClient(app) as test_client:
            response = test_client.post("/v1/research", json={"objective": "x"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_cancel_is_idempotent_and_records_one_durable_event(client) -> None:
    test_client, factory = client
    task_id = test_client.post("/v1/research", json={"objective": "cancel me"}).json()[
        "task_id"
    ]

    first = test_client.post(f"/v1/tasks/{task_id}/cancel")
    second = test_client.post(f"/v1/tasks/{task_id}/cancel")

    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "cancel_requested"
    events = _events(factory, uuid.UUID(task_id))
    assert [(event.sequence, event.stage) for event in events] == [
        (1, "created"),
        (2, "cancellation"),
    ]


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_retry_requeues_partial_task_and_enforces_attempt_cap(client) -> None:
    test_client, factory = client
    task_id = uuid.UUID(
        test_client.post("/v1/research", json={"objective": "retry me"}).json()[
            "task_id"
        ]
    )

    async def mark_partial(attempt):
        async with factory() as session:
            task = await session.get(ResearchTask, task_id)
            task.status = TaskStatus.partial
            task.attempt = attempt
            await session.commit()

    asyncio.run(mark_partial(1))
    accepted = test_client.post(f"/v1/tasks/{task_id}/retry")
    assert accepted.status_code == 202
    assert accepted.json() == {
        "task_id": str(task_id),
        "status": "queued",
        "attempt": 2,
    }

    asyncio.run(mark_partial(3))
    rejected = test_client.post(f"/v1/tasks/{task_id}/retry")
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "retry_not_allowed"
