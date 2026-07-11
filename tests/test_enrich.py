"""Contract tests for grounded LLM snippet enrichment."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from rancho.config import get_settings
from rancho.enrich import SnippetEnricher
from rancho.extract import ContentUnavailableError, FetchedPage
from rancho.llm import LLMUnavailableError
from rancho.main import app, get_search_adapter, get_snippet_enricher
from rancho.models import SearchResult

client = TestClient(app)

_PAGE = "Apache Cassandra is a wide-column NoSQL store built for high write throughput."
_GROUNDED = "wide-column NoSQL store built for high write throughput"


def _result(
    url: str, snippet: str = "provider snippet", number: int = 1
) -> SearchResult:
    return SearchResult(
        url=url,
        title=f"Result {number}",
        snippet=snippet,
        source_id=f"src_{number:02d}",
        retrieved_at=datetime.now(timezone.utc),
    )


class _FakeFetcher:
    def __init__(self, pages=None, fail_urls=None):
        self._pages = pages or {}
        self._fail = set(fail_urls or [])
        self.fetched: list[str] = []

    def fetch(self, url: str) -> FetchedPage:
        self.fetched.append(url)
        if url in self._fail:
            raise ContentUnavailableError
        return FetchedPage(final_url=url, markdown=self._pages.get(url, _PAGE))


class _FakeLLM:
    def __init__(self, reply: str = "", unavailable: bool = False):
        self._reply = reply
        self._unavailable = unavailable
        self.calls: list = []

    def complete(
        self, messages, *, high_effort=False, temperature=0.0, max_output_tokens=512
    ):
        self.calls.append(messages)
        if self._unavailable:
            raise LLMUnavailableError
        return self._reply


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
def test_grounded_excerpt_replaces_provider_snippet() -> None:
    enricher = SnippetEnricher(_FakeLLM(reply=_GROUNDED), _FakeFetcher(), 3)

    results, warnings = enricher.enrich(
        "cassandra", [_result("https://a.example/")], []
    )

    assert results[0].snippet == _GROUNDED
    assert warnings == []


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
def test_paraphrase_is_not_grounded_and_falls_back() -> None:
    enricher = SnippetEnricher(
        _FakeLLM(reply="It is a distributed NoSQL database."), _FakeFetcher(), 3
    )

    results, warnings = enricher.enrich(
        "cassandra", [_result("https://a.example/")], []
    )

    assert results[0].snippet == "provider snippet"
    assert warnings == []  # ordinary fallback is not an error


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
def test_fetch_refused_falls_back_with_redacted_warning() -> None:
    fetcher = _FakeFetcher(fail_urls=["https://a.example/"])
    enricher = SnippetEnricher(_FakeLLM(reply=_GROUNDED), fetcher, 3)

    results, warnings = enricher.enrich(
        "cassandra", [_result("https://a.example/")], []
    )

    assert results[0].snippet == "provider snippet"
    assert len(warnings) == 1
    for leaked in ("example", "http", "cassandra.apache"):
        assert leaked not in warnings[0]


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
def test_model_unavailable_falls_back_with_warning() -> None:
    enricher = SnippetEnricher(_FakeLLM(unavailable=True), _FakeFetcher(), 3)

    results, warnings = enricher.enrich(
        "cassandra", [_result("https://a.example/")], []
    )

    assert results[0].snippet == "provider snippet"
    assert len(warnings) == 1


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
def test_only_top_n_results_are_enriched() -> None:
    fetcher = _FakeFetcher()
    enricher = SnippetEnricher(_FakeLLM(reply=_GROUNDED), fetcher, 2)
    results = [_result(f"https://a.example/{i}", number=i) for i in range(1, 6)]

    enriched, _ = enricher.enrich("cassandra", results, [])

    assert fetcher.fetched == ["https://a.example/1", "https://a.example/2"]
    assert enriched[0].snippet == _GROUNDED
    assert [r.snippet for r in enriched[2:]] == ["provider snippet"] * 3


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
def test_page_content_is_passed_as_delimited_untrusted_context() -> None:
    llm = _FakeLLM(reply=_GROUNDED)
    enricher = SnippetEnricher(llm, _FakeFetcher(), 3)

    enricher.enrich("cassandra", [_result("https://a.example/")], [])

    user_message = llm.calls[0][1]["content"]
    assert "<content>" in user_message and "</content>" in user_message
    assert "Query: cassandra" in user_message
    assert _PAGE in user_message


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
def test_one_result_failure_does_not_fail_the_batch() -> None:
    fetcher = _FakeFetcher(
        pages={"https://ok.example/": _PAGE}, fail_urls=["https://bad.example/"]
    )
    enricher = SnippetEnricher(_FakeLLM(reply=_GROUNDED), fetcher, 3)
    results = [
        _result("https://bad.example/", number=1),
        _result("https://ok.example/", number=2),
    ]

    enriched, warnings = enricher.enrich("cassandra", results, [])

    assert enriched[0].snippet == "provider snippet"
    assert enriched[1].snippet == _GROUNDED
    assert len(warnings) == 1


class _EndpointAdapter:
    """A minimal non-orchestrator adapter for the /v1/search endpoint."""

    def __init__(self, results: list[SearchResult]):
        self._results = results

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        return self._results

    def check_ready(self) -> None:
        return None


def _configure_search(monkeypatch) -> None:
    monkeypatch.setenv("RANCHO_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("RANCHO_SEARCH_BASE_URL", "http://searxng.internal")
    get_settings.cache_clear()


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#acceptance-evidence]
def test_endpoint_provider_snippet_when_disabled(monkeypatch) -> None:
    _configure_search(monkeypatch)  # RANCHO_SEARCH_ENRICH unset -> disabled
    adapter = _EndpointAdapter(
        [_result("https://a.example/", snippet="provider snippet")]
    )
    app.dependency_overrides[get_search_adapter] = lambda: adapter
    try:
        response = client.post("/v1/search", json={"query": "cassandra"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["results"][0]["snippet"] == "provider snippet"


# @spec[RANCHO_SNIPPET_SYNTHESIS.md#acceptance-evidence]
def test_endpoint_replaces_snippet_with_grounded_excerpt(monkeypatch) -> None:
    _configure_search(monkeypatch)
    adapter = _EndpointAdapter(
        [_result("https://a.example/", snippet="provider snippet")]
    )
    enricher = SnippetEnricher(_FakeLLM(reply=_GROUNDED), _FakeFetcher(), 3)
    app.dependency_overrides[get_search_adapter] = lambda: adapter
    app.dependency_overrides[get_snippet_enricher] = lambda: enricher
    try:
        response = client.post("/v1/search", json={"query": "cassandra"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["results"][0]["snippet"] == _GROUNDED
