"""Contract tests for durable monitors, change detection, and webhooks."""

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rancho.db import Base
from rancho.db_models import Evidence, Monitor, MonitorRun, ResearchTask, TaskStatus
from rancho.monitors import (
    WebhookDeliveryError,
    deliver_webhook,
    evidence_snapshot,
    finalize_monitor_task,
    launch_due_monitors,
    record_monitor_run,
)


def _evidence(task_id, url, digest):
    return Evidence(
        task_id=task_id,
        canonical_url=url,
        original_url=url,
        content="body",
        content_sha256=digest,
        retrieved_at=datetime.now(timezone.utc),
    )


# @spec[RANCHO_FINDALL_AND_MONITORS.md#acceptance-evidence]
def test_evidence_snapshot_is_canonical_and_deterministic():
    task_id = uuid.uuid4()
    evidence = [
        _evidence(task_id, "https://b.example", "b" * 64),
        _evidence(task_id, "https://a.example", "a" * 64),
    ]

    assert list(evidence_snapshot(evidence).items()) == [
        ("https://a.example", "a" * 64),
        ("https://b.example", "b" * 64),
    ]


# @spec[RANCHO_FINDALL_AND_MONITORS.md#acceptance-evidence]
def test_monitor_runs_detect_only_material_hash_changes(tmp_path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            monitor = Monitor(
                objective="watch",
                output_schema={"name": "string"},
                interval_minutes=60,
                request_fingerprint="0" * 64,
                next_run_at=datetime.now(timezone.utc),
            )
            first = ResearchTask(
                objective="first", task_type="findall", status=TaskStatus.completed
            )
            second = ResearchTask(
                objective="second", task_type="findall", status=TaskStatus.completed
            )
            session.add_all([monitor, first, second])
            await session.flush()
            one = await record_monitor_run(
                session, monitor, first, [_evidence(first.id, "https://a", "1" * 64)]
            )
            two = await record_monitor_run(
                session, monitor, second, [_evidence(second.id, "https://a", "2" * 64)]
            )
        await engine.dispose()
        return one, two

    baseline, changed = asyncio.run(scenario())
    assert baseline.material_change is False
    assert baseline.outcome == "unchanged"
    assert changed.material_change is True
    assert changed.outcome == "changed"


# @spec[RANCHO_FINDALL_AND_MONITORS.md#acceptance-evidence]
def test_webhook_is_https_signed_bounded_and_secret_free():
    secret = "a-very-long-monitor-secret"
    monitor = Monitor(
        id=uuid.uuid4(),
        objective="watch",
        output_schema={"name": "string"},
        interval_minutes=60,
        webhook_url="https://hooks.example.test/change",
        webhook_secret=secret,
        request_fingerprint="0" * 64,
        next_run_at=datetime.now(timezone.utc),
    )
    run = MonitorRun(
        id=uuid.uuid4(),
        monitor_id=monitor.id,
        task_id=uuid.uuid4(),
        input={},
        evidence_hashes={},
        outcome="changed",
        material_change=True,
        next_run_at=datetime.now(timezone.utc),
    )

    def handler(request):
        body = request.content
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert request.headers["X-Rancho-Signature"] == f"sha256={expected}"
        assert secret.encode() not in body
        assert json.loads(body)["material_change"] is True
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        assert deliver_webhook(monitor, run, client) is True
    finally:
        client.close()


def test_webhook_rejects_insecure_or_credentialed_urls():
    for url in ("http://hooks.example/x", "https://user:pass@hooks.example/x"):
        monitor = Monitor(
            id=uuid.uuid4(),
            objective="x",
            output_schema={},
            interval_minutes=60,
            webhook_url=url,
            webhook_secret="long-enough-secret",
            request_fingerprint="0" * 64,
            next_run_at=datetime.now(timezone.utc),
        )
        run = MonitorRun(
            id=uuid.uuid4(),
            monitor_id=monitor.id,
            task_id=uuid.uuid4(),
            input={},
            evidence_hashes={},
            outcome="changed",
            material_change=True,
            next_run_at=datetime.now(timezone.utc),
        )
        with pytest.raises(WebhookDeliveryError):
            deliver_webhook(monitor, run)


def test_due_launcher_is_unique_and_recovers_queued_dispatch(tmp_path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'due.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        async with factory() as session:
            monitor = Monitor(
                objective="watch",
                output_schema={"name": "string"},
                interval_minutes=60,
                request_fingerprint="0" * 64,
                next_run_at=datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc),
            )
            session.add(monitor)
            await session.commit()
            monitor_id = monitor.id
        dispatched = []

        async def enqueue(task_id):
            dispatched.append(task_id)

        first = await launch_due_monitors(factory, enqueue, now=now)
        second = await launch_due_monitors(factory, enqueue, now=now)
        async with factory() as session:
            tasks = list((await session.execute(select(ResearchTask))).scalars().all())
            monitor = await session.get(Monitor, monitor_id)
        await engine.dispose()
        return first, second, tasks, monitor, dispatched

    first, second, tasks, monitor, dispatched = asyncio.run(scenario())
    assert len(first) == 1 and second == [] and len(tasks) == 1
    assert tasks[0].scheduled_for.isoformat().startswith("2026-01-01T10:30")
    assert monitor.next_run_at.isoformat().startswith("2026-01-01T12:30")
    assert dispatched == [tasks[0].id, tasks[0].id]


def test_monitor_task_finalization_is_idempotent(tmp_path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'final.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            monitor = Monitor(
                objective="watch",
                output_schema={"name": "string"},
                interval_minutes=60,
                request_fingerprint="0" * 64,
                next_run_at=datetime.now(timezone.utc),
            )
            session.add(monitor)
            await session.flush()
            task = ResearchTask(
                objective="watch",
                task_type="findall",
                status=TaskStatus.completed,
                monitor_id=monitor.id,
                scheduled_for=datetime.now(timezone.utc),
            )
            session.add(task)
            await session.flush()
            session.add(_evidence(task.id, "https://a", "1" * 64))
            await session.commit()
            task_id = task.id
        first = await finalize_monitor_task(factory, task_id)
        second = await finalize_monitor_task(factory, task_id)
        async with factory() as session:
            runs = list((await session.execute(select(MonitorRun))).scalars().all())
        await engine.dispose()
        return first, second, runs

    first, second, runs = asyncio.run(scenario())
    assert first.id == second.id and len(runs) == 1
    assert runs[0].webhook_status == "not_required"
