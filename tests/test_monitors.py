"""Contract tests for durable monitors, change detection, and webhooks."""

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rancho.db import Base
from rancho.db_models import Evidence, Monitor, MonitorRun, ResearchTask, TaskStatus
from rancho.monitors import (
    WebhookDeliveryError,
    deliver_webhook,
    evidence_snapshot,
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
