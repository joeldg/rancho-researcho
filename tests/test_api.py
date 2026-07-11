"""Contract tests for the Phase 1 HTTP surface."""

import httpx
from fastapi.testclient import TestClient

from rancho.config import get_settings
from rancho.main import app
from rancho.search import SearxngSearchAdapter, get_search_adapter

client = TestClient(app)


# @spec[RANCHO_API_SECURITY.md#acceptance-evidence]
def reset_settings() -> None:
    """Ensure every test reads only its explicit environment configuration."""
    get_settings.cache_clear()


# @spec[RANCHO_API_SECURITY.md#http-contract]
def test_health_is_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# @spec[RANCHO_API_SECURITY.md#http-contract]
def test_ready_is_unavailable_without_search_provider(monkeypatch) -> None:
    monkeypatch.delenv("RANCHO_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("RANCHO_SEARCH_BASE_URL", raising=False)
    reset_settings()

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["reason"] == "search_provider_unconfigured"


# @spec[RANCHO_API_SECURITY.md#http-contract]
def test_metrics_exposes_provider_configuration(monkeypatch) -> None:
    monkeypatch.delenv("RANCHO_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("RANCHO_SEARCH_BASE_URL", raising=False)
    reset_settings()

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "rancho_search_provider_configured 0" in response.text


# @spec[RANCHO_API_SECURITY.md#acceptance-evidence]
def test_search_never_fabricates_results_without_provider(monkeypatch) -> None:
    monkeypatch.delenv("RANCHO_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("RANCHO_SEARCH_BASE_URL", raising=False)
    reset_settings()

    response = client.post(
        "/v1/search",
        json={"query": "solid-state batteries", "max_results": 5},
    )

    body = response.json()
    assert response.status_code == 503
    assert body["error"]["code"] == "provider_unavailable"
    assert body["request_id"].startswith("req_")


# @spec[RANCHO_API_SECURITY.md#acceptance-evidence]
def test_search_rejects_unknown_request_fields() -> None:
    response = client.post(
        "/v1/search",
        json={"query": "solid-state batteries", "unsupported": True},
    )

    assert response.status_code == 422


# @spec[RANCHO_API_SECURITY.md#tests-and-evidence]
def test_search_normalizes_and_deduplicates_searxng_results(monkeypatch) -> None:
    observed_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request
        observed_request = request
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "results": [
                    {
                        "url": "https://example.com/article#section",
                        "title": "First result",
                        "content": "An evidence-bearing excerpt.",
                    },
                    {
                        "url": "https://example.com/article",
                        "title": "Duplicate result",
                        "content": "This record is deduplicated.",
                    },
                    {
                        "url": "https://second.example/report",
                        "title": "Second result",
                        "content": "Another evidence-bearing excerpt.",
                    },
                ]
            },
        )

    monkeypatch.setenv("RANCHO_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("RANCHO_SEARCH_BASE_URL", "http://searxng.internal/ignored")
    reset_settings()
    provider_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = SearxngSearchAdapter(
        "http://searxng.internal/ignored",
        client=provider_client,
    )
    app.dependency_overrides[get_search_adapter] = lambda: adapter
    try:
        response = client.post(
            "/v1/search", json={"query": "solid-state batteries", "max_results": 2}
        )
    finally:
        app.dependency_overrides.clear()
        provider_client.close()

    assert response.status_code == 200
    assert observed_request is not None
    assert str(observed_request.url) == (
        "http://searxng.internal/search?q=solid-state+batteries&format=json"
    )
    assert response.json()["provider"] == "rancho-agent"
    assert [item["source_id"] for item in response.json()["results"]] == [
        "src_01",
        "src_02",
    ]
    assert len(response.json()["results"]) == 2


# @spec[RANCHO_API_SECURITY.md#tests-and-evidence]
def test_search_redacts_provider_failure(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="SENSITIVE PROVIDER DETAILS")

    monkeypatch.setenv("RANCHO_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("RANCHO_SEARCH_BASE_URL", "http://searxng.internal")
    reset_settings()
    provider_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = SearxngSearchAdapter("http://searxng.internal", client=provider_client)
    app.dependency_overrides[get_search_adapter] = lambda: adapter
    try:
        response = client.post("/v1/search", json={"query": "battery research"})
    finally:
        app.dependency_overrides.clear()
        provider_client.close()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert "SENSITIVE" not in response.text


# @spec[RANCHO_API_SECURITY.md#tests-and-evidence]
def test_search_rejects_provider_redirect_without_following_it(monkeypatch) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private-service"},
        )

    monkeypatch.setenv("RANCHO_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("RANCHO_SEARCH_BASE_URL", "http://searxng.internal")
    reset_settings()
    provider_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = SearxngSearchAdapter("http://searxng.internal", client=provider_client)
    app.dependency_overrides[get_search_adapter] = lambda: adapter
    try:
        response = client.post("/v1/search", json={"query": "redirect test"})
    finally:
        app.dependency_overrides.clear()
        provider_client.close()

    assert response.status_code == 503
    assert requested_urls == [
        "http://searxng.internal/search?q=redirect+test&format=json"
    ]


# @spec[RANCHO_API_SECURITY.md#http-contract]
def test_ready_reports_unreachable_configured_provider(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("provider unavailable", request=request)

    monkeypatch.setenv("RANCHO_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("RANCHO_SEARCH_BASE_URL", "http://searxng.internal")
    reset_settings()
    provider_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = SearxngSearchAdapter("http://searxng.internal", client=provider_client)
    app.dependency_overrides[get_search_adapter] = lambda: adapter
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()
        provider_client.close()

    assert response.status_code == 503
    assert response.json()["reason"] == "search_provider_unreachable"


# @spec[RANCHO_API_SECURITY.md#tests-and-evidence]
def test_adapter_never_fetches_result_urls(monkeypatch) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "results": [
                    {
                        "url": "http://127.0.0.1/private-service",
                        "title": "Untrusted result URL",
                        "content": "This is only returned as search metadata.",
                    }
                ]
            },
        )

    monkeypatch.setenv("RANCHO_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("RANCHO_SEARCH_BASE_URL", "http://searxng.internal")
    reset_settings()
    provider_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = SearxngSearchAdapter("http://searxng.internal", client=provider_client)
    app.dependency_overrides[get_search_adapter] = lambda: adapter
    try:
        response = client.post("/v1/search", json={"query": "private service"})
    finally:
        app.dependency_overrides.clear()
        provider_client.close()

    assert response.status_code == 200
    assert requested_urls == [
        "http://searxng.internal/search?q=private+service&format=json"
    ]
