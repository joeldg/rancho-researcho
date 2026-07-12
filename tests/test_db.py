"""Migration and durable-constraint tests for the Phase 2 persistence layer."""

import asyncio
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rancho.db import Base
from rancho.db_models import (
    Claim,
    EventType,
    Evidence,
    ResearchTask,
    TaskEvent,
    TaskStatus,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DURABLE_TABLES = {
    "research_tasks",
    "evidence",
    "claims",
    "claim_evidence",
    "task_events",
    "candidates",
    "candidate_evidence",
}


def _alembic_config(db_url: str, monkeypatch) -> Config:
    monkeypatch.setenv("RANCHO_ALEMBIC_URL", db_url)
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    return config


def _sqlite_tables(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        connection.close()
    return {row[0] for row in rows}


def _sqlite_columns(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        connection.close()
    return {row[1] for row in rows}


# @spec[RANCHO_ASYNC_RESEARCH.md#security-observability-and-tests]
def test_migration_upgrade_then_downgrade(tmp_path, monkeypatch) -> None:
    db_file = tmp_path / "durable.db"
    config = _alembic_config(f"sqlite+aiosqlite:///{db_file}", monkeypatch)

    command.upgrade(config, "head")
    assert _DURABLE_TABLES <= _sqlite_tables(db_file)
    assert "final_result" in _sqlite_columns(db_file, "research_tasks")

    command.downgrade(config, "base")
    assert _DURABLE_TABLES.isdisjoint(_sqlite_tables(db_file))


def _make_sessionmaker(tmp_path) -> async_sessionmaker:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    return async_sessionmaker(engine, expire_on_commit=False)


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
def test_task_status_defaults_to_queued(tmp_path) -> None:
    sessionmaker = _make_sessionmaker(tmp_path)

    async def _run() -> TaskStatus:
        async with sessionmaker() as session:
            task = ResearchTask(objective="find things", budget_max_sources=5)
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task.status

    assert asyncio.run(_run()) is TaskStatus.queued


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
def test_duplicate_task_event_sequence_is_rejected(tmp_path) -> None:
    sessionmaker = _make_sessionmaker(tmp_path)

    async def _run() -> None:
        async with sessionmaker() as session:
            task = ResearchTask(objective="o", budget_max_sources=1)
            session.add(task)
            await session.flush()
            session.add(
                TaskEvent(
                    task_id=task.id,
                    sequence=1,
                    type=EventType.task_created,
                    payload={},
                )
            )
            await session.commit()
            task_id = task.id

        async with sessionmaker() as session:
            session.add(
                TaskEvent(
                    task_id=task_id,
                    sequence=1,
                    type=EventType.progress,
                    payload={},
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    asyncio.run(_run())


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
def test_claim_references_retained_evidence(tmp_path) -> None:
    sessionmaker = _make_sessionmaker(tmp_path)

    async def _run() -> list[str]:
        from datetime import datetime, timezone

        async with sessionmaker() as session:
            task = ResearchTask(objective="o", budget_max_sources=1)
            session.add(task)
            await session.flush()
            evidence = Evidence(
                task_id=task.id,
                canonical_url="https://example.com/a",
                original_url="https://example.com/a",
                content="body",
                content_sha256="0" * 64,
                retrieved_at=datetime.now(timezone.utc),
            )
            claim = Claim(task_id=task.id, text="a fact", evidence=[evidence])
            session.add(claim)
            await session.commit()
            claim_id = claim.id

        async with sessionmaker() as session:
            reloaded = await session.get(Claim, claim_id)
            await session.refresh(reloaded, ["evidence"])
            return [str(item.canonical_url) for item in reloaded.evidence]

    assert asyncio.run(_run()) == ["https://example.com/a"]
