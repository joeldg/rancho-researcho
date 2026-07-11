# Rancho Search Adapters and Orchestration Contract

## Scope

This project-scoped contract governs search provider adapters beyond SearXNG (a DuckDuckGo
adapter, and optional Google/Bing developer overrides) and the orchestrator that fans a query
across the active adapters, normalizes their records, and returns one deduplicated result set. It
narrows `RANCHO_API_SECURITY.md` and `SECURITY_AND_SECRETS.md` for the multi-provider search
surface.

## Intent

Rancho aggregates results from multiple operator-approved search sources without fabricating
results, without becoming an open proxy, and without leaking which upstream engines were queried.
A single provider failure degrades honestly rather than failing the whole request, and a total
failure is reported as an explicit unavailable response.

## Requirements

1. Every adapter implements the existing `SearchAdapter` protocol (`search`, `check_ready`),
   returning normalized `SearchResult` values or raising `ProviderUnavailableError`. As with
   `SearxngSearchAdapter`, `search` normalizes and deduplicates only; it never fetches result
   URLs.
2. Each adapter calls only its own fixed provider endpoint with bounded connect/read timeouts, a
   bounded response size, and no redirects. The host, scheme, port, and path are operator
   configuration or adapter constants and are never derived from a caller request or a search
   result, consistent with `RANCHO_API_SECURITY.md`.
3. Google and Bing adapters are optional and inactive unless explicitly configured with operator
   API keys. Keys are secret per `SECURITY_AND_SECRETS.md`: sent only as outbound authorization,
   never logged, returned, or placed in errors. Absent configuration makes an adapter inactive,
   not an error.
4. The orchestrator runs only the active configured adapters, each under a bounded timeout and an
   overall bound. A single adapter failure does not fail the request while at least one active
   adapter returns results. If every active adapter fails, the API returns the redacted HTTP 503
   `provider_unavailable` response.
5. Results from all adapters are merged and deduplicated by canonical URL (reusing the existing
   canonicalization), bounded to the request `max_results`. Ordering is deterministic and stable
   across runs, and the orchestrator assigns each returned result its `source_id`.
6. Provider identity and provider errors are redacted: the response never reveals which upstream
   engines were queried or any raw provider error body. `warnings` may note partial degradation
   without naming a provider host or secret.
7. Active providers are selected by explicit operator configuration (for example a
   `RANCHO_SEARCH_PROVIDERS` list). Selection is never derived from a caller request or result.
   The existing single-SearXNG configuration continues to work unchanged.
8. Tests use `httpx.MockTransport` or controlled fakes and cover per-adapter normalization,
   cross-adapter deduplication, partial-failure degradation, total-failure 503, bounded sizes and
   timeouts, and secret redaction. They make no live network request.

## Non-Goals

This contract does not define web page fetching or content extraction (a separate contract),
relevance ranking or scoring models, per-tenant provider policy, or result caching.

## Acceptance Evidence

- A controlled fixture shows a query fanned across two active adapters returning a single
  deduplicated, bounded, deterministically ordered result set.
- A fixture with one failing and one healthy adapter returns the healthy results with a redacted
  degradation warning; a fixture with all adapters failing returns the redacted 503.
- A secret-redaction fixture proves no provider API key or raw provider error body reaches the
  response, warnings, or logs.
- Code trace mappings connect each adapter, the orchestrator, configuration, and tests to this
  contract.

## Token Budget Class

Project contract.

## Related Specs

- `RANCHO_API_SECURITY.md`
- `SECURITY_AND_SECRETS.md`
- `GLOBAL_SECURITY.md`
- `RANCHO_PROJECT_PROFILE.md`

## AI Agent Directives

Implement additional adapters and the orchestrator only after this contract is reviewed and
published. Never fabricate results, never expose provider identity or errors, never allow
caller-controlled provider or endpoint selection, and preserve the existing single-provider
configuration path.
