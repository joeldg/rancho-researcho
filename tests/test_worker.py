"""Controlled worker tests for durable bounded evidence collection."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from rancho.db import Base
from rancho.db_models import Evidence, ResearchTask, TaskEvent, TaskStatus
from rancho.extract import ContentUnavailableError, FetchedPage
from rancho.models import SearchResult
from rancho.research import create_or_get_research_task
from rancho.search import OrchestratedSearch
from rancho.worker import run_research_task


class _Search:
    def __init__(self, results):
        self._results = results

    def run(self, objective, budget):
        del objective
        return OrchestratedSearch(results=self._results[:budget])


class _Fetcher:
    def __init__(self, pages):
        self._pages = pages

    def fetch(self, url):
        page = self._pages[url]
        if isinstance(page, Exception):
            raise page
        return page


def _result(number):
    return SearchResult(
        url=f"https://example{number}.com/article",
        title=f"Source {number}",
        snippet="Provider excerpt",
        source_id=f"src_{number:02d}",
        retrieved_at=datetime.now(timezone.utc),
    )


def test_worker_persists_safe_evidence_and_ordered_redacted_events(tmp_path):
    async def scenario():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}", poolclass=NullPool
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            task, _ = await create_or_get_research_task(
                session, "battery research", 2, None
            )
        first, second = _result(1), _result(2)
        fetcher = _Fetcher(
            {
                str(first.url): FetchedPage(
                    final_url=str(first.url), markdown="# Tested evidence\nUseful fact."
                ),
                str(second.url): ContentUnavailableError(),
            }
        )

        await run_research_task(
            {
                "session_factory": factory,
                "search": _Search([first, second]),
                "fetcher": fetcher,
            },
            str(task.id),
        )

        async with factory() as session:
            persisted = await session.get(ResearchTask, task.id)
            evidence = (await session.execute(select(Evidence))).scalars().all()
            events = (
                await session.execute(
                    select(TaskEvent)
                    .where(TaskEvent.task_id == task.id)
                    .order_by(TaskEvent.sequence)
                )
            ).scalars().all()
        await engine.dispose()
        return persisted, evidence, events

    task, evidence, events = asyncio.run(scenario())

    assert task.status is TaskStatus.partial
    assert len(evidence) == 1
    assert evidence[0].canonical_url == "https://example1.com/article"
    assert evidence[0].content_sha256
    assert [(event.sequence, event.type.value) for event in events] == [
        (1, "task.created"),
        (2, "stage.started"),
        (3, "progress"),
        (4, "search.completed"),
        (5, "evidence.extracted"),
        (6, "evidence.extracted"),
        (7, "task.partial"),
    ]
    assert events[4].payload == {"source_id": "src_01", "outcome": "stored"}
    assert events[5].payload == {"source_id": "src_02", "outcome": "unavailable"}
    assert "example2" not in str(events[5].payload)


def test_worker_honestly_completes_partial_when_search_is_unavailable(tmp_path):
    class _UnavailableSearch:
        def run(self, objective, budget):
            del objective, budget
            from rancho.search import ProviderUnavailableError

            raise ProviderUnavailableError

    async def scenario():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'unavailable.db'}", poolclass=NullPool
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            task, _ = await create_or_get_research_task(session, "unavailable", 1, None)
        await run_research_task(
            {"session_factory": factory, "search": _UnavailableSearch()}, str(task.id)
        )
        async with factory() as session:
            persisted = await session.get(ResearchTask, task.id)
            events = (
                await session.execute(
                    select(TaskEvent)
                    .where(TaskEvent.task_id == task.id)
                    .order_by(TaskEvent.sequence)
                )
            ).scalars().all()
        await engine.dispose()
        return persisted, events

    task, events = asyncio.run(scenario())

    assert task.status is TaskStatus.partial
    assert events[3].payload == {"result_count": 0, "degraded": True}
    assert events[-1].payload == {"reason": "synthesis_not_implemented"}
