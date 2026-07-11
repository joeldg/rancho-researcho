"""Contract tests for durable task-event SSE replay."""

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from rancho.db import Base, get_session_factory
from rancho.db_models import EventType, ResearchTask, TaskEvent, TaskStatus
from rancho.main import app


@pytest.fixture
def client(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'events.db'}", poolclass=NullPool
    )

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app.dependency_overrides[get_session_factory] = lambda: factory
    try:
        with TestClient(app) as test_client:
            yield test_client, factory
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _terminal_task(factory):
    async def create():
        async with factory() as session:
            task = ResearchTask(
                objective="test event replay",
                budget_max_sources=1,
                status=TaskStatus.partial,
            )
            session.add(task)
            await session.flush()
            session.add_all(
                [
                    TaskEvent(
                        task_id=task.id,
                        sequence=1,
                        type=EventType.task_created,
                        stage="created",
                        payload={"status": "queued"},
                    ),
                    TaskEvent(
                        task_id=task.id,
                        sequence=2,
                        type=EventType.stage_started,
                        stage="search",
                        payload={},
                    ),
                    TaskEvent(
                        task_id=task.id,
                        sequence=3,
                        type=EventType.task_partial,
                        stage="synthesis",
                        payload={"reason": "synthesis_not_implemented"},
                    ),
                ]
            )
            await session.commit()
            return task.id

    return asyncio.run(create())


def _events(response_text):
    chunks = [chunk for chunk in response_text.split("\n\n") if chunk]
    parsed = []
    for chunk in chunks:
        lines = dict(line.split(": ", 1) for line in chunk.splitlines())
        parsed.append((int(lines["id"]), lines["event"], json.loads(lines["data"])))
    return parsed


# @spec[RANCHO_ASYNC_RESEARCH.md#sse-and-events]
def test_events_replay_ordered_durable_history_with_sse_ids(client):
    test_client, factory = client
    task_id = _terminal_task(factory)

    response = test_client.get(f"/v1/tasks/{task_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert [(sequence, name) for sequence, name, _ in events] == [
        (1, "task.created"),
        (2, "stage.started"),
        (3, "task.partial"),
    ]
    assert events[-1][2] == {
        "task_id": str(task_id),
        "sequence": 3,
        "timestamp": events[-1][2]["timestamp"],
        "stage": "synthesis",
        "data": {"reason": "synthesis_not_implemented"},
    }


# @spec[RANCHO_ASYNC_RESEARCH.md#sse-and-events]
def test_events_last_event_id_replays_only_newer_events(client):
    test_client, factory = client
    task_id = _terminal_task(factory)

    response = test_client.get(
        f"/v1/tasks/{task_id}/events", headers={"Last-Event-ID": "2"}
    )

    assert [(sequence, name) for sequence, name, _ in _events(response.text)] == [
        (3, "task.partial")
    ]


# @spec[RANCHO_ASYNC_RESEARCH.md#sse-and-events]
def test_events_reject_missing_or_invalid_replay_history(client):
    test_client, factory = client
    task_id = _terminal_task(factory)

    missing = test_client.get(
        f"/v1/tasks/{task_id}/events", headers={"Last-Event-ID": "99"}
    )
    invalid = test_client.get(
        f"/v1/tasks/{task_id}/events", headers={"Last-Event-ID": "nope"}
    )

    assert missing.status_code == 410
    assert invalid.status_code == 410
    assert missing.json()["error"]["code"] == "event_history_expired"


# @spec[RANCHO_ASYNC_RESEARCH.md#sse-and-events]
def test_events_return_404_for_unknown_task(client):
    test_client, _ = client

    response = test_client.get(f"/v1/tasks/{uuid.uuid4()}/events")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "task_not_found"
