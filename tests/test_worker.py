"""Controlled worker tests for durable bounded evidence collection."""

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from rancho.config import Settings
from rancho.db import Base
from rancho.db_models import (
    Claim,
    EventType,
    Evidence,
    ResearchTask,
    TaskEvent,
    TaskStatus,
)
from rancho.extract import ContentUnavailableError, FetchedPage
from rancho.llm import LLMUnavailableError
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
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
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
            {
                "session_factory": factory,
                "search": _UnavailableSearch(),
                "llm": None,
            },
            str(task.id),
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
    assert events[-1].payload == {"reason": "research_incomplete"}


# @spec[RANCHO_CLAIM_VERIFICATION.md#acceptance-evidence]
def test_worker_persists_verified_claims_and_completes_after_verification(tmp_path):
    async def scenario():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'verified.db'}", poolclass=NullPool
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            task, _ = await create_or_get_research_task(session, "verified", 1, None)
        result = _result(1)
        fetcher = _Fetcher(
            {
                str(result.url): FetchedPage(
                    final_url=str(result.url), markdown="A retained fact."
                )
            }
        )

        # Run collection first with a model that learns the generated evidence UUID
        # from the prompt and returns one supported candidate.
        class _EvidenceAwareLLM:
            def complete(self, messages, **kwargs):
                del kwargs
                if "EVIDENCE_JSON" in messages[0]["content"]:
                    return '```json\n{"complete":true,"queries":[]}\n```'
                bundle = json.loads(messages[1]["content"])["evidence"]
                item = bundle[0]
                return "Result:\n```json\n" + json.dumps(
                    {
                        "claims": [
                            {
                                "text": "A verified fact",
                                "evidence_ids": [item["evidence_id"]],
                                "citation_urls": [item["canonical_url"]],
                            },
                            {
                                "text": "Unsupported model text",
                                "evidence_ids": [],
                                "citation_urls": [],
                            },
                        ]
                    }
                ) + "\n```"

        await run_research_task(
            {
                "session_factory": factory,
                "search": _Search([result]),
                "fetcher": fetcher,
                "llm": _EvidenceAwareLLM(),
            },
            str(task.id),
        )
        async with factory() as session:
            persisted = await session.get(ResearchTask, task.id)
            claims = (await session.execute(select(Claim))).scalars().all()
            events = (
                (
                    await session.execute(
                        select(TaskEvent)
                        .where(TaskEvent.task_id == task.id)
                        .order_by(TaskEvent.sequence)
                    )
                )
                .scalars()
                .all()
            )
        await engine.dispose()
        return persisted, claims, events

    task, claims, events = asyncio.run(scenario())

    assert task.status is TaskStatus.completed
    assert [claim.text for claim in claims] == ["A verified fact"]
    assert "Unsupported model text" not in task.final_result
    assert "https://example1.com/article" in task.final_result
    assert [event.type.value for event in events[-2:]] == [
        "claim.verified",
        "task.completed",
    ]


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#acceptance-evidence]
def test_worker_runs_bounded_multi_step_evaluation_and_avoids_duplicates(tmp_path):
    class _IterativeSearch:
        def __init__(self, first, second):
            self.first = first
            self.second = second
            self.queries = []

        def run(self, query, budget):
            self.queries.append((query, budget))
            if query == "initial objective":
                return OrchestratedSearch(results=[self.first])
            return OrchestratedSearch(results=[self.first, self.second])

    class _IterativeLLM:
        def complete(self, messages, **kwargs):
            del kwargs
            if "EVIDENCE_JSON" in messages[0]["content"]:
                return json.dumps(
                    {"complete": False, "queries": ["secondary gap query"]}
                )
            evidence = json.loads(messages[1]["content"])["evidence"]
            return json.dumps(
                {
                    "claims": [
                        {
                            "text": "Two-step verified result",
                            "evidence_ids": [item["evidence_id"] for item in evidence],
                            "citation_urls": [
                                item["canonical_url"] for item in evidence
                            ],
                        }
                    ]
                }
            )

    async def scenario():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'iterative.db'}", poolclass=NullPool
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            task, _ = await create_or_get_research_task(
                session, "initial objective", 3, None
            )
        first, second = _result(1), _result(2)
        search = _IterativeSearch(first, second)
        fetcher = _Fetcher(
            {
                str(first.url): FetchedPage(
                    final_url=str(first.url), markdown="First evidence"
                ),
                str(second.url): FetchedPage(
                    final_url=str(second.url), markdown="Second evidence"
                ),
            }
        )
        await run_research_task(
            {
                "session_factory": factory,
                "search": search,
                "fetcher": fetcher,
                "llm": _IterativeLLM(),
                "settings": Settings(
                    research_max_iterations=2,
                    research_max_planner_tokens=64,
                    research_max_model_tokens=512,
                ),
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
        return persisted, evidence, events, search.queries, fetcher.calls

    task, evidence, events, queries, fetch_calls = asyncio.run(scenario())

    assert task.status is TaskStatus.completed
    assert len(evidence) == 2
    assert [query for query, _ in queries] == [
        "initial objective",
        "secondary gap query",
    ]
    assert fetch_calls == [str(_result(1).url), str(_result(2).url)]
    assert [event.type.value for event in events] == [
        "task.created",
        "stage.started",
        "progress",
        "search.completed",
        "evidence.extracted",
        "progress",
        "search.completed",
        "evidence.extracted",
        "claim.verified",
        "task.completed",
    ]


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#acceptance-evidence]
def test_worker_cancels_after_search_before_fetch(tmp_path):
    class _CancellingSearch:
        def __init__(self, factory, task_id, result):
            self.factory = factory
            self.task_id = task_id
            self.result = result

        def run(self, query, budget):
            del query, budget

            async def cancel():
                async with self.factory() as session:
                    task = await session.get(ResearchTask, self.task_id)
                    task.status = TaskStatus.cancel_requested
                    await session.commit()

            asyncio.run(cancel())
            return OrchestratedSearch(results=[self.result])

    async def scenario():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'cancel.db'}", poolclass=NullPool
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            task, _ = await create_or_get_research_task(session, "cancel", 1, None)
        result = _result(1)
        await run_research_task(
            {
                "session_factory": factory,
                "search": _CancellingSearch(factory, task.id, result),
                "fetcher": _Fetcher({}),
            },
            str(task.id),
        )
        async with factory() as session:
            persisted = await session.get(ResearchTask, task.id)
            evidence = (await session.execute(select(Evidence))).scalars().all()
        await engine.dispose()
        return persisted, evidence

    task, evidence = asyncio.run(scenario())

    assert task.status is TaskStatus.cancelled
    assert evidence == []


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#acceptance-evidence]
def test_worker_finishes_partial_when_evaluation_model_fails(tmp_path):
    class _FailingLLM:
        def complete(self, messages, **kwargs):
            del messages, kwargs
            raise LLMUnavailableError

    async def scenario():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'model-failure.db'}",
            poolclass=NullPool,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            task, _ = await create_or_get_research_task(session, "evaluate", 2, None)
        result = _result(1)
        await run_research_task(
            {
                "session_factory": factory,
                "search": _Search([result]),
                "fetcher": _Fetcher(
                    {
                        str(result.url): FetchedPage(
                            final_url=str(result.url), markdown="Evidence"
                        )
                    }
                ),
                "llm": _FailingLLM(),
            },
            str(task.id),
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
    assert events[-1].payload == {"reason": "evaluation_unavailable"}


# @spec[RANCHO_ASYNC_RESEARCH.md#task-lifecycle-and-worker-behavior]
def test_worker_records_redacted_failed_terminal_state_on_unexpected_error(tmp_path):
    class _CrashingFetcher:
        def fetch(self, url):
            del url
            raise RuntimeError("secret internal detail")

    async def scenario():
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'unexpected.db'}", poolclass=NullPool
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            task, _ = await create_or_get_research_task(session, "unexpected", 1, None)
        await run_research_task(
            {
                "session_factory": factory,
                "search": _Search([_result(1)]),
                "fetcher": _CrashingFetcher(),
                "llm": None,
            },
            str(task.id),
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

    assert task.status is TaskStatus.failed
    assert events[-1].type is EventType.task_failed
    assert events[-1].payload == {"reason": "internal_unavailable"}
    assert "secret internal detail" not in str(events[-1].payload)
