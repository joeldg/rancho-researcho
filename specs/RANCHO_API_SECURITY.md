# Rancho HTTP API and Retrieval Security Contract

## Scope

This project-scoped contract governs the Phase 1 HTTP surface, configuration, SearXNG search
adapter, provider availability behavior, and outbound retrieval boundary for Rancho Researcho.

## Intent

Rancho must never claim a search occurred when it did not, and it must keep configured provider
infrastructure separate from untrusted URLs discovered in search results or supplied by callers.

## Requirements

### HTTP contract

1. `POST /v1/search` accepts a non-empty `query` of at most 2,000 characters and a
   `max_results` value from 1 through 20. Unknown request fields are rejected.
2. A successful response contains `results`, `provider`, `request_id`, and `warnings`. Each
   result contains `url`, `title`, `snippet`, `source_id`, and `retrieved_at`; results are
   deduplicated by canonical URL and never exceed the requested limit.
3. If no provider can process a request, return HTTP 503 with `error.code` equal to
   `provider_unavailable` and a generated request ID. Do not return synthetic results,
   citations, adapter diagnostics, or secrets.
4. `/health` reports process health without configuration details. `/ready` distinguishes an
   unconfigured or unreachable provider from readiness. `/metrics` exposes only redacted,
   Prometheus-compatible health and request-count signals.

### Provider configuration and SearXNG

5. `RANCHO_SEARCH_PROVIDER=searxng` and `RANCHO_SEARCH_BASE_URL` select the SearXNG JSON
   adapter. The base URL is administrator-controlled configuration, never request input.
   `RANCHO_SEARCH_API_KEY`, if configured, is secret material and must not be serialized into
   API responses, exceptions, logs, metrics, or traces.
6. A configured SearXNG base URL is a trusted control-plane endpoint. It may use an internal
   Docker hostname, loopback address, or private address only when supplied by trusted runtime
   configuration; callers and search-result data must have no path to alter its host, port,
   scheme, path, or headers. Production exposure of Rancho remains HTTPS; this exception does
   not make the SearXNG endpoint public.
7. The adapter sends a bounded GET request only to the configured SearXNG `/search` path with
   `q`, `format=json`, and a bounded result count. It uses a connect timeout of at most three
   seconds, a read timeout of at most ten seconds, follows no redirects, accepts only a JSON
   response, and rejects a response body larger than one MiB.
8. A malformed SearXNG response, response with a non-JSON content type, timeout, connection
   failure, redirect, or non-success status produces the redacted `provider_unavailable`
   response. The raw provider body and URL query are not returned to the caller.

### Untrusted outbound destinations

9. A URL from a caller, search result, redirect, or crawled page is untrusted and must not be
   fetched by the SearXNG adapter. Before a future extractor or crawler opens such a URL, it
   must allow only `http` or `https`, reject credentials and non-default unsafe ports, resolve
   the hostname immediately before each connection, and reject every loopback, unspecified,
   multicast, link-local, private, reserved, and metadata-service address. Redirect targets
   repeat the complete validation before a request is sent.
10. A future untrusted-content client must pin its connection to an address validated for that
    request or abort when resolution changes; it must not rely solely on a preflight DNS lookup.
    It must impose explicit connect/read/write/pool timeouts, a decompressed body-size cap,
    MIME allowlist, redirect limit, and redacted audit outcome.

### Tests and evidence

11. Contract tests cover successful normalized SearXNG results, result limiting and
    deduplication, unavailable-provider handling, validation errors, and the absence of secrets
    in API or metrics responses. Adapter tests use recorded fixtures, `httpx.MockTransport`, or
    a controlled local test server; they do not make live network requests.
12. Security tests prove that an untrusted loopback/private URL and an untrusted redirect to one
    are rejected before a connection, while a configured SearXNG control-plane URL can be used
    only through the adapter's fixed path and query construction.

## Non-Goals

This contract does not authorize unauthenticated public exposure, browser automation, an
unbounded crawler, arbitrary request proxying, or outbound extraction in the SearXNG slice.

## Acceptance Evidence

- Tests show a configured SearXNG fixture yielding bounded, deduplicated normalized results.
- Tests show 503 `provider_unavailable` for configuration, timeout, redirect, malformed JSON,
  and non-success failures without exposing provider details.
- Tests demonstrate the control-plane/untrusted-destination boundary and redaction behavior.
- Code trace mappings connect API routes, request/response schemas, adapter, and tests to the
  relevant sections of this contract.

## Token Budget Class

Project contract.

## Related Specs

- `RANCHO_PROJECT_PROFILE.md`
- `GLOBAL_SECURITY.md`
- `SECURITY_AND_SECRETS.md`
- `TRACEABILITY_AND_OBSERVABILITY.md`

## AI Agent Directives

Implement only the SearXNG control-plane client in this slice. Do not add a generic URL fetcher,
crawler, or private-address exemption for untrusted input without the validation and connection
pinning requirements above plus their tests.

