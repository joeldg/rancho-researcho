"""Controlled tests for authoritative structured research planning."""

import json

from rancho.planning import plan_queries


class _LLM:
    def __init__(self, response):
        self.response = response
        self.messages = None

    def complete(self, messages, **kwargs):
        del kwargs
        self.messages = messages
        return self.response


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#requirements]
def test_planner_accepts_fenced_bounded_queries_and_directs_primary_sources():
    llm = _LLM(
        "Plan:\n```json\n"
        + json.dumps({"queries": ["site:python.org Python 3.14 release"]})
        + "\n```"
    )

    queries = plan_queries(llm, "Latest Python release", 2, 128)

    assert queries == ["site:python.org Python 3.14 release"]
    assert "authoritative primary sources" in llm.messages[0]["content"]


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#requirements]
def test_planner_rejects_prose_and_ambiguity_then_bounds_extra_queries():
    assert plan_queries(_LLM("Search official sources."), "objective", 2, 128) == []
    assert plan_queries(
        _LLM('{"queries":["one"]}\n{"queries":["two"]}'),
        "objective",
        2,
        128,
    ) == []
    assert plan_queries(
        _LLM('{"queries":["one","two","three"]}'), "objective", 2, 128
    ) == ["one", "two"]


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#requirements]
def test_planner_accepts_bounded_query_and_rationale_shape():
    response = json.dumps(
        {
            "queries": [
                {"query": "site:sqlite.org WAL", "rationale": "Official docs"},
                {"query": "ignored over budget", "rationale": "Extra"},
            ]
        }
    )

    assert plan_queries(_LLM(response), "objective", 1, 128) == [
        "site:sqlite.org WAL"
    ]


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#requirements]
def test_planner_recovers_only_authoritative_queries_from_weak_wrappers():
    markdown = """Here are suggestions.
1. ```
site:www.sqlite.org WAL network filesystem
```
Do something unrelated.
2. ```
site:www.sqlite.org WAL checkpoint starvation
```
"""
    truncated_json = (
        'Explanation\n```json\n{"queries":['
        '"site:github.com self-hosted metasearch",'
    )

    assert plan_queries(_LLM(markdown), "objective", 2, 128) == [
        "site:www.sqlite.org WAL network filesystem",
        "site:www.sqlite.org WAL checkpoint starvation",
    ]
    assert plan_queries(_LLM(truncated_json), "objective", 2, 128) == [
        "site:github.com self-hosted metasearch"
    ]


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#requirements]
def test_planner_does_not_execute_unfenced_model_prose_as_a_query():
    assert plan_queries(
        _LLM("Try searching for open source metasearch engines."),
        "objective",
        2,
        128,
    ) == []
