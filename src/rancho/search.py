"""Configured search-provider adapters for Rancho Researcho."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import Depends

from rancho.config import Settings, get_settings
from rancho.models import SearchResult

_MAX_PROVIDER_RESPONSE_BYTES = 1_048_576
_PROVIDER_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=3.0)


class ProviderUnavailableError(Exception):
    """Raised when a configured provider cannot safely answer a request."""


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
class SearchAdapter(Protocol):
    """A bounded provider interface used by the HTTP API."""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return normalized results or raise ProviderUnavailableError."""

    def check_ready(self) -> None:
        """Raise ProviderUnavailableError when the provider cannot be reached."""


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
        return _normalize_results(raw_results, max_results)

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
        if self._client is not None:
            return self._client.get(
                self._endpoint,
                params={"q": query, "format": "json"},
                headers=headers,
                follow_redirects=False,
                timeout=_PROVIDER_TIMEOUT,
            )
        with httpx.Client(
            timeout=_PROVIDER_TIMEOUT,
            follow_redirects=False,
            headers=headers,
        ) as client:
            return client.get(
                self._endpoint,
                params={"q": query, "format": "json"},
            )


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
def get_search_adapter(
    settings: Settings = Depends(get_settings),
) -> SearchAdapter | None:
    """Build the sole supported configured search adapter."""
    if not settings.search_is_configured or settings.search_base_url is None:
        return None
    return SearxngSearchAdapter(
        base_url=str(settings.search_base_url),
        api_key=settings.search_api_key,
    )


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
def _searxng_endpoint(base_url: str) -> str:
    """Discard configured paths so requests cannot become arbitrary proxies."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderUnavailableError
    return urlunsplit((parsed.scheme, parsed.netloc, "/search", "", ""))


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
def _validate_provider_response(response: httpx.Response) -> None:
    """Enforce bounded JSON-only, redirect-free provider responses."""
    if response.is_redirect or not response.is_success:
        raise ProviderUnavailableError
    content_type = response.headers.get("content-type", "")
    if content_type.split(";", maxsplit=1)[0].strip().lower() != "application/json":
        raise ProviderUnavailableError
    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise ProviderUnavailableError
    if len(response.content) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise ProviderUnavailableError


# @spec[RANCHO_API_SECURITY.md#http-contract]
def _normalize_results(
    raw_results: list[object], max_results: int
) -> list[SearchResult]:
    """Validate, de-duplicate, and bound provider records without fetching URLs."""
    results: list[SearchResult] = []
    canonical_urls: set[str] = set()
    retrieved_at = datetime.now(timezone.utc)
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            continue
        result = _normalize_result(raw_result, len(results) + 1, retrieved_at)
        if result is None:
            continue
        canonical_url = _canonical_url(str(result.url))
        if canonical_url in canonical_urls:
            continue
        canonical_urls.add(canonical_url)
        results.append(result)
        if len(results) == max_results:
            break
    return results


# @spec[RANCHO_API_SECURITY.md#http-contract]
def _normalize_result(
    raw_result: dict[object, object], source_number: int, retrieved_at: datetime
) -> SearchResult | None:
    """Convert one SearXNG record into the public result contract."""
    url = raw_result.get("url")
    title = raw_result.get("title")
    snippet = raw_result.get("content")
    values = (url, title, snippet)
    if not all(isinstance(value, str) and value.strip() for value in values):
        return None
    try:
        return SearchResult(
            url=url,
            title=title.strip()[:500],
            snippet=snippet.strip()[:2_000],
            source_id=f"src_{source_number:02d}",
            retrieved_at=retrieved_at,
        )
    except ValueError:
        return None


# @spec[RANCHO_API_SECURITY.md#http-contract]
def _canonical_url(url: str) -> str:
    """Return the stable URL identity used only for result de-duplication."""
    parsed = urlsplit(url)
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")
    )
