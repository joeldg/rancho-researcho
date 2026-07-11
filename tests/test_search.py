"""Contract tests for the multi-provider search adapters and orchestrator."""

from datetime import datetime, timezone

import httpx
import pytest

from rancho.config import Settings
from rancho.models import SearchResult
from rancho.search import (
    BingSearchAdapter,
    DuckDuckGoSearchAdapter,
    ProviderUnavailableError,
    SearchOrchestrator,
)


def _result(url: str, number: int) -> SearchResult:
    return SearchResult(
        url=url,
        title=f"Result {number}",
        snippet=f"Evidence excerpt {number}.",
        source_id=f"src_{number:02d}",
        retrieved_at=datetime.now(timezone.utc),
    )


class _FakeAdapter:
    """A deterministic in-memory adapter for orchestrator tests."""

    def __init__(
        self,
        results: list[SearchResult] | None = None,
        *,
        fails: bool = False,
        unreachable: bool = False,
    ) -> None:
        self._results = results or []
        self._fails = fails
        self._unreachable = unreachable

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        if self._fails:
            raise ProviderUnavailableError
        return self._results

    def check_ready(self) -> None:
        if self._unreachable:
            raise ProviderUnavailableError


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_active_providers_resolve_from_explicit_list() -> None:
    settings = Settings(
        _env_file=None, search_providers="duckduckgo, bing", bing_api_key="k"
    )
    assert settings.active_search_providers() == ["duckduckgo", "bing"]


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_bing_is_inactive_without_a_key() -> None:
    settings = Settings(_env_file=None, search_providers="bing")
    assert settings.active_search_providers() == []
    assert settings.search_is_configured is False


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_single_searxng_configuration_is_preserved() -> None:
    settings = Settings(
        _env_file=None,
        search_provider="searxng",
        search_base_url="http://searxng:8080",
    )
    assert settings.active_search_providers() == ["searxng"]


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_duckduckgo_flattens_and_normalizes_related_topics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.duckduckgo.com"
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "RelatedTopics": [
                    {"FirstURL": "https://example.com/a", "Text": "Alpha topic"},
                    {
                        "Name": "Group",
                        "Topics": [
                            {
                                "FirstURL": "https://example.com/b",
                                "Text": "Beta topic",
                            }
                        ],
                    },
                    {"Text": "no url, dropped"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        results = DuckDuckGoSearchAdapter(client=client).search("q", 5)
    finally:
        client.close()

    assert [str(r.url) for r in results] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert results[0].title == "Alpha topic"


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_duckduckgo_accepts_x_javascript_content_type() -> None:
    """The live Instant Answer API serves JSON as application/x-javascript."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            202,
            headers={"content-type": "application/x-javascript"},
            content=b'{"RelatedTopics": [{"FirstURL": "https://example.com/z",'
            b' "Text": "Zeta"}]}',
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        results = DuckDuckGoSearchAdapter(client=client).search("q", 5)
    finally:
        client.close()

    assert [str(r.url) for r in results] == ["https://example.com/z"]


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_bing_sends_key_as_header_only_and_normalizes() -> None:
    seen_key: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_key.append(request.headers.get("Ocp-Apim-Subscription-Key"))
        # The key must never appear in the query string.
        assert "secret-bing-key" not in str(request.url)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "webPages": {
                    "value": [
                        {
                            "url": "https://example.com/x",
                            "name": "Result X",
                            "snippet": "Excerpt X.",
                        }
                    ]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        results = BingSearchAdapter("secret-bing-key", client=client).search("q", 5)
    finally:
        client.close()

    assert seen_key == ["secret-bing-key"]
    assert [str(r.url) for r in results] == ["https://example.com/x"]
    assert all("secret-bing-key" not in r.snippet for r in results)


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_bing_failure_is_redacted_and_leaks_no_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="SENSITIVE PROVIDER BODY secret-bing-key")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ProviderUnavailableError) as error:
            BingSearchAdapter("secret-bing-key", client=client).search("q", 5)
    finally:
        client.close()

    assert "SENSITIVE" not in str(error.value)
    assert "secret-bing-key" not in str(error.value)


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_oversized_provider_response_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-length": str(2_000_000),
            },
            json={"RelatedTopics": []},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ProviderUnavailableError):
            DuckDuckGoSearchAdapter(client=client).search("q", 5)
    finally:
        client.close()


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_orchestrator_merges_and_deduplicates_across_adapters() -> None:
    first = _FakeAdapter(
        [_result("https://example.com/a#frag", 1), _result("https://example.com/b", 2)]
    )
    second = _FakeAdapter(
        [_result("https://example.com/a", 9), _result("https://third.example/c", 3)]
    )

    outcome = SearchOrchestrator([first, second]).run("q", 5)

    assert [str(r.url) for r in outcome.results] == [
        "https://example.com/a#frag",
        "https://example.com/b",
        "https://third.example/c",
    ]
    # req 5: the orchestrator reassigns deterministic source ids.
    assert [r.source_id for r in outcome.results] == ["src_01", "src_02", "src_03"]
    assert outcome.warnings == []


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_orchestrator_bounds_results_to_max() -> None:
    adapter = _FakeAdapter(
        [_result(f"https://example.com/{i}", i) for i in range(1, 6)]
    )

    outcome = SearchOrchestrator([adapter]).run("q", 2)

    assert len(outcome.results) == 2


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_orchestrator_degrades_on_partial_failure_without_naming_provider() -> None:
    healthy = _FakeAdapter([_result("https://example.com/a", 1)])
    failing = _FakeAdapter(fails=True)

    outcome = SearchOrchestrator([healthy, failing]).run("q", 5)

    assert [str(r.url) for r in outcome.results] == ["https://example.com/a"]
    assert len(outcome.warnings) == 1
    warning = outcome.warnings[0].lower()
    assert "partial" in warning
    for leaked in ("bing", "duckduckgo", "searxng", "http"):
        assert leaked not in warning


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_orchestrator_total_failure_raises() -> None:
    orchestrator = SearchOrchestrator(
        [_FakeAdapter(fails=True), _FakeAdapter(fails=True)]
    )

    with pytest.raises(ProviderUnavailableError):
        orchestrator.run("q", 5)


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_orchestrator_ready_when_any_adapter_reachable() -> None:
    orchestrator = SearchOrchestrator(
        [_FakeAdapter(unreachable=True), _FakeAdapter()]
    )
    orchestrator.check_ready()  # does not raise


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def test_orchestrator_not_ready_when_all_unreachable() -> None:
    orchestrator = SearchOrchestrator(
        [_FakeAdapter(unreachable=True), _FakeAdapter(unreachable=True)]
    )
    with pytest.raises(ProviderUnavailableError):
        orchestrator.check_ready()
