"""Contract tests for the Phase 1 HTTP surface."""

from fastapi.testclient import TestClient

from rancho.config import get_settings
from rancho.main import app

client = TestClient(app)


# @spec[RANCHO_API_SECURITY.md#acceptance-evidence]
def reset_settings() -> None:
    """Ensure every test reads only its explicit environment configuration."""
    get_settings.cache_clear()


# @spec[RANCHO_API_SECURITY.md#requirements]
def test_health_is_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# @spec[RANCHO_API_SECURITY.md#requirements]
def test_ready_is_unavailable_without_search_provider(monkeypatch) -> None:
    monkeypatch.delenv("RANCHO_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("RANCHO_SEARCH_BASE_URL", raising=False)
    reset_settings()

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["reason"] == "search_provider_unconfigured"


# @spec[RANCHO_API_SECURITY.md#requirements]
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
