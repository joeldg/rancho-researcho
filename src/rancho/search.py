"""Configured search-provider adapters and orchestration for Rancho Researcho."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import Depends

from rancho.config import Settings, get_settings
from rancho.models import SearchResult

_MAX_PROVIDER_RESPONSE_BYTES = 1_048_576
_PROVIDER_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=3.0)
_DUCKDUCKGO_ENDPOINT = "https://api.duckduckgo.com/"
_BING_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"
_JSON_CONTENT_TYPES = frozenset({"application/json"})
# The DuckDuckGo Instant Answer API serves JSON as application/x-javascript.
_DUCKDUCKGO_CONTENT_TYPES = frozenset(
    {"application/json", "application/x-javascript", "text/javascript"}
)


class ProviderUnavailableError(Exception):
    """Raised when a configured provider cannot safely answer a request."""


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
class SearchAdapter(Protocol):
    """A bounded provider interface used by the HTTP API."""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return normalized results or raise ProviderUnavailableError."""

    def check_ready(self) -> None:
        """Raise ProviderUnavailableError when the provider cannot be reached."""


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
@dataclass
class OrchestratedSearch:
    """A merged multi-provider result set with redacted degradation warnings."""

    results: list[SearchResult]
    warnings: list[str] = field(default_factory=list)


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
class SearxngSearchAdapter:
    """A fixed-path JSON client for the administrator-configured SearXNG service."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._endpoint = _searxng_endpoint(base_url)
        self._api_key = api_key
        self._client = client

    # @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Request fixed-path SearXNG JSON and return bounded normalized results."""
        try:
            response = self._request(query)
            _validate_provider_response(response)
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ProviderUnavailableError from error

        if not isinstance(payload, dict):
            raise ProviderUnavailableError
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise ProviderUnavailableError
        return _normalize_records(raw_results, max_results, _extract_searxng)

    # @spec[RANCHO_API_SECURITY.md#http-contract]
    def check_ready(self) -> None:
        """Verify the configured provider can serve bounded JSON requests."""
        try:
            _validate_provider_response(self._request("rancho readiness"))
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ProviderUnavailableError from error

    # @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
    def _request(self, query: str) -> httpx.Response:
        """Call only the configured provider endpoint with fixed request semantics."""
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        params = {"q": query, "format": "json"}
        return _bounded_get(self._client, self._endpoint, params, headers)


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
class DuckDuckGoSearchAdapter:
    """A fixed-endpoint client for the DuckDuckGo Instant Answer JSON API."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    # @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return bounded normalized results from the DuckDuckGo JSON endpoint."""
        try:
            response = self._request(query)
            _validate_provider_response(response, _DUCKDUCKGO_CONTENT_TYPES)
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ProviderUnavailableError from error

        if not isinstance(payload, dict):
            raise ProviderUnavailableError
        records = _duckduckgo_flatten(payload.get("RelatedTopics"))
        return _normalize_records(records, max_results, _extract_duckduckgo)

    # @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
    def check_ready(self) -> None:
        """Verify the DuckDuckGo endpoint serves bounded JSON."""
        try:
            _validate_provider_response(
                self._request("rancho readiness"), _DUCKDUCKGO_CONTENT_TYPES
            )
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ProviderUnavailableError from error

    def _request(self, query: str) -> httpx.Response:
        headers = {"Accept": "application/json"}
        params = {"q": query, "format": "json", "no_html": "1", "no_redirect": "1"}
        return _bounded_get(self._client, _DUCKDUCKGO_ENDPOINT, params, headers)


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
class BingSearchAdapter:
    """An optional key-gated client for the Bing Web Search API.

    The subscription key is sent only as an outbound authorization header and is
    never logged, returned, or placed in an error.
    """

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client

    # @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return bounded normalized results from the Bing Web Search API."""
        try:
            response = self._request(query, max_results)
            _validate_provider_response(response)
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ProviderUnavailableError from error

        if not isinstance(payload, dict):
            raise ProviderUnavailableError
        web_pages = payload.get("webPages")
        values = web_pages.get("value") if isinstance(web_pages, dict) else None
        if not isinstance(values, list):
            raise ProviderUnavailableError
        return _normalize_records(values, max_results, _extract_bing)

    # @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
    def check_ready(self) -> None:
        """Verify the Bing endpoint serves bounded JSON for the configured key."""
        try:
            _validate_provider_response(self._request("rancho readiness", 1))
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise ProviderUnavailableError from error

    def _request(self, query: str, max_results: int) -> httpx.Response:
        headers = {
            "Accept": "application/json",
            "Ocp-Apim-Subscription-Key": self._api_key,
        }
        params = {"q": query, "count": max(1, min(max_results, 20))}
        return _bounded_get(self._client, _BING_ENDPOINT, params, headers)


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
class SearchOrchestrator:
    """Fan a query across active adapters into one deduplicated result set."""

    def __init__(self, adapters: Iterable[SearchAdapter]) -> None:
        self._adapters: list[SearchAdapter] = list(adapters)

    # @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
    def run(self, query: str, max_results: int) -> OrchestratedSearch:
        """Merge active-adapter results; degrade on partial failure, 503 on total."""
        merged: list[SearchResult] = []
        seen: set[str] = set()
        failures = 0
        for adapter in self._adapters:
            try:
                adapter_results = adapter.search(query, max_results)
            except ProviderUnavailableError:
                failures += 1
                continue
            for result in adapter_results:
                canonical_url = _canonical_url(str(result.url))
                if canonical_url in seen:
                    continue
                seen.add(canonical_url)
                merged.append(result)
                if len(merged) == max_results:
                    break
            if len(merged) == max_results:
                break

        if failures == len(self._adapters):
            raise ProviderUnavailableError

        warnings: list[str] = []
        if failures:
            # Redacted: never name which upstream engine degraded.
            warnings.append(
                "One or more search providers were unavailable; "
                "results may be partial."
            )
        renumbered = [
            result.model_copy(update={"source_id": f"src_{index:02d}"})
            for index, result in enumerate(merged, start=1)
        ]
        return OrchestratedSearch(results=renumbered, warnings=warnings)

    # @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
    def check_ready(self) -> None:
        """Ready when at least one active adapter is reachable."""
        for adapter in self._adapters:
            try:
                adapter.check_ready()
                return
            except ProviderUnavailableError:
                continue
        raise ProviderUnavailableError


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def get_search_adapter(
    settings: Settings = Depends(get_settings),
) -> SearchOrchestrator | None:
    """Build an orchestrator over the operator-selected active providers."""
    adapters = _build_active_adapters(settings)
    if not adapters:
        return None
    return SearchOrchestrator(adapters)


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def _build_active_adapters(settings: Settings) -> list[SearchAdapter]:
    """Instantiate one adapter per configured, buildable active provider."""
    adapters: list[SearchAdapter] = []
    for name in settings.active_search_providers():
        if name == "searxng" and settings.search_base_url is not None:
            adapters.append(
                SearxngSearchAdapter(
                    base_url=str(settings.search_base_url),
                    api_key=settings.search_api_key,
                )
            )
        elif name == "duckduckgo":
            adapters.append(DuckDuckGoSearchAdapter())
        elif name == "bing" and settings.bing_api_key:
            adapters.append(BingSearchAdapter(api_key=settings.bing_api_key))
    return adapters


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
def _searxng_endpoint(base_url: str) -> str:
    """Discard configured paths so requests cannot become arbitrary proxies."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderUnavailableError
    return urlunsplit((parsed.scheme, parsed.netloc, "/search", "", ""))


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def _bounded_get(
    client: httpx.Client | None,
    url: str,
    params: dict[str, object],
    headers: dict[str, str],
) -> httpx.Response:
    """Issue a redirect-free, bounded GET to a fixed provider endpoint only."""
    if client is not None:
        return client.get(
            url,
            params=params,
            headers=headers,
            follow_redirects=False,
            timeout=_PROVIDER_TIMEOUT,
        )
    with httpx.Client(
        timeout=_PROVIDER_TIMEOUT,
        follow_redirects=False,
        headers=headers,
    ) as owned:
        return owned.get(url, params=params)


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
def _validate_provider_response(
    response: httpx.Response,
    allowed_content_types: frozenset[str] = _JSON_CONTENT_TYPES,
) -> None:
    """Enforce bounded, redirect-free, JSON-bearing provider responses."""
    if response.is_redirect or not response.is_success:
        raise ProviderUnavailableError
    content_type = response.headers.get("content-type", "")
    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    if media_type not in allowed_content_types:
        raise ProviderUnavailableError
    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise ProviderUnavailableError
    if len(response.content) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise ProviderUnavailableError


# @spec[RANCHO_API_SECURITY.md#http-contract]
def _normalize_records(
    raw_records: list[object],
    max_results: int,
    extract: Callable[[dict[object, object]], tuple[object, object, object] | None],
) -> list[SearchResult]:
    """Validate, de-duplicate, and bound provider records without fetching URLs."""
    results: list[SearchResult] = []
    canonical_urls: set[str] = set()
    retrieved_at = datetime.now(timezone.utc)
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            continue
        fields = extract(raw_record)
        if fields is None:
            continue
        url, title, snippet = fields
        if not all(isinstance(value, str) and value.strip() for value in fields):
            continue
        canonical_url = _canonical_url(str(url))
        if canonical_url in canonical_urls:
            continue
        try:
            result = SearchResult(
                url=str(url),
                title=str(title).strip()[:500],
                snippet=str(snippet).strip()[:2_000],
                source_id=f"src_{len(results) + 1:02d}",
                retrieved_at=retrieved_at,
            )
        except ValueError:
            continue
        canonical_urls.add(canonical_url)
        results.append(result)
        if len(results) == max_results:
            break
    return results


# @spec[RANCHO_API_SECURITY.md#http-contract]
def _extract_searxng(
    record: dict[object, object],
) -> tuple[object, object, object] | None:
    """Map one SearXNG record to (url, title, snippet)."""
    return record.get("url"), record.get("title"), record.get("content")


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def _extract_duckduckgo(
    record: dict[object, object],
) -> tuple[object, object, object] | None:
    """Map one DuckDuckGo topic to (url, title, snippet) from its text."""
    text = record.get("Text")
    url = record.get("FirstURL")
    return url, text, text


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def _extract_bing(
    record: dict[object, object],
) -> tuple[object, object, object] | None:
    """Map one Bing web result to (url, title, snippet)."""
    return record.get("url"), record.get("name"), record.get("snippet")


# @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
def _duckduckgo_flatten(related_topics: object) -> list[object]:
    """Flatten DuckDuckGo RelatedTopics, including nested topic groups."""
    flattened: list[object] = []
    if not isinstance(related_topics, list):
        return flattened
    for topic in related_topics:
        if not isinstance(topic, dict):
            continue
        nested = topic.get("Topics")
        if isinstance(nested, list):
            flattened.extend(_duckduckgo_flatten(nested))
        elif "FirstURL" in topic:
            flattened.append(topic)
    return flattened


# @spec[RANCHO_API_SECURITY.md#http-contract]
def _canonical_url(url: str) -> str:
    """Return the stable URL identity used only for result de-duplication."""
    parsed = urlsplit(url)
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")
    )
