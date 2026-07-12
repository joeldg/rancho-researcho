"""Durable monitor scheduling, change detection, and signed webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rancho.db_models import Evidence, Monitor, MonitorRun, ResearchTask, TaskStatus
from rancho.research import ResearchConflictError

_WEBHOOK_TIMEOUT = httpx.Timeout(5.0)


class WebhookDeliveryError(Exception):
    """A redacted failure at the opt-in webhook boundary."""


# @spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
async def create_or_get_monitor(
    session: AsyncSession,
    *,
    objective: str,
    output_schema: dict[str, str],
    interval_minutes: int,
    webhook_url: str | None,
    webhook_secret: str | None,
    idempotency_key: str | None,
    now: datetime | None = None,
) -> tuple[Monitor, bool]:
    payload = json.dumps(
        {
            "objective": objective,
            "output_schema": output_schema,
            "interval_minutes": interval_minutes,
            "webhook_url": webhook_url,
            "webhook_secret_sha256": (
                hashlib.sha256(webhook_secret.encode()).hexdigest()
                if webhook_secret
                else None
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    if idempotency_key:
        existing = await session.scalar(
            select(Monitor).where(Monitor.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise ResearchConflictError
            return existing, False
    start = now or datetime.now(timezone.utc)
    monitor = Monitor(
        objective=objective,
        output_schema=output_schema,
        interval_minutes=interval_minutes,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        next_run_at=start + timedelta(minutes=interval_minutes),
    )
    session.add(monitor)
    await session.commit()
    return monitor, True


def evidence_snapshot(evidence: list[Evidence]) -> dict[str, str]:
    """Return a deterministic canonical URL to content-hash snapshot."""
    return dict(sorted((item.canonical_url, item.content_sha256) for item in evidence))


# @spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
async def record_monitor_run(
    session: AsyncSession,
    monitor: Monitor,
    task: ResearchTask,
    evidence: list[Evidence],
    now: datetime | None = None,
) -> MonitorRun:
    if task.status is not TaskStatus.completed:
        raise ValueError("monitor task is not completed")
    snapshot = evidence_snapshot(evidence)
    previous = await session.scalar(
        select(MonitorRun)
        .where(MonitorRun.monitor_id == monitor.id)
        .order_by(MonitorRun.created_at.desc())
        .limit(1)
    )
    material_change = previous is not None and previous.evidence_hashes != snapshot
    observed = now or datetime.now(timezone.utc)
    next_run = observed + timedelta(minutes=monitor.interval_minutes)
    run = MonitorRun(
        monitor_id=monitor.id,
        task_id=task.id,
        input={"objective": monitor.objective, "output_schema": monitor.output_schema},
        evidence_hashes=snapshot,
        outcome="changed" if material_change else "unchanged",
        material_change=material_change,
        next_run_at=next_run,
    )
    monitor.next_run_at = next_run
    session.add(run)
    await session.commit()
    return run


# @spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
def deliver_webhook(
    monitor: Monitor,
    run: MonitorRun,
    client: httpx.Client | None = None,
) -> bool:
    """Deliver a signed minimal alert only for a material change."""
    if not run.material_change or not monitor.webhook_url:
        return False
    if not monitor.webhook_secret or not _safe_webhook_url(monitor.webhook_url):
        raise WebhookDeliveryError
    payload = {
        "monitor_id": str(monitor.id),
        "run_id": str(run.id),
        "outcome": run.outcome,
        "material_change": True,
        "next_run_at": run.next_run_at.isoformat(),
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(
        monitor.webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    owned = client is None
    sender = client or httpx.Client(timeout=_WEBHOOK_TIMEOUT, follow_redirects=False)
    try:
        response = sender.post(
            monitor.webhook_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Rancho-Signature": f"sha256={signature}",
            },
            timeout=_WEBHOOK_TIMEOUT,
            follow_redirects=False,
        )
        if not response.is_success or response.is_redirect:
            raise WebhookDeliveryError
    except (httpx.HTTPError, ValueError) as error:
        raise WebhookDeliveryError from error
    finally:
        if owned:
            sender.close()
    return True


def _safe_webhook_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.port in {None, 443}
    )
