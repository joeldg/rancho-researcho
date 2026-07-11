# Rancho HTTP API and Retrieval Security Contract (Draft)

## Scope

This draft governs the Phase 1 HTTP surface, configuration, unavailable-provider behavior, and
the security boundary for future outbound retrieval in Rancho Researcho.

## Intent

Make it impossible for the service to silently claim research occurred when no adapter was
available, and make the retrieval boundary explicit before outbound HTTP is implemented.

## Requirements

1. `POST /v1/search` accepts a non-empty `query` and a bounded `max_results`; unknown request
   fields are rejected.
2. A successful search response has `results`, `provider`, `request_id`, and `warnings` fields.
   Each result has `url`, `title`, `snippet`, `source_id`, and `retrieved_at`.
3. If no provider can process a request, return HTTP 503 with an error code of
   `provider_unavailable` and a generated request ID. Never return synthetic results.
4. `/health` reports process health without configuration details. `/ready` must distinguish an
   unconfigured search provider from readiness. `/metrics` must never expose credentials.
5. Provider URLs and API keys are configuration only. API keys must not be serialized into
   response payloads, exceptions, logs, or metrics.
6. Before an adapter fetches any remote URL, it must validate every resolved destination and
   redirect target, reject loopback/private/link-local/metadata ranges, cap response and
   decompressed sizes, set timeouts, restrict MIME types, and record a redacted outcome.
7. The implementation must use contract tests for success, validation, and unavailable-provider
   cases. Network adapter tests must use recorded fixtures or controlled local test servers.

## Non-Goals

This draft does not authorize unauthenticated production exposure, browser automation, or an
unbounded crawler.

## Acceptance Evidence

- Tests exercise 503 provider-unavailable behavior and reject unknown fields.
- A review of configuration and metrics confirms no configured secret is returned.
- Future adapter tests exercise a blocked private or redirect destination before live retrieval.

## Token Budget Class

Project contract.

## Related Specs

- `PROJECT_DESCRIPTION.md`
- `GLOBAL_SECURITY.md`
- `SECURITY_AND_SECRETS.md`
- `TRACEABILITY_AND_OBSERVABILITY.md`

## AI Agent Directives

Treat this as draft guidance only until review. Do not implement outbound retrieval unless the
SSRF requirements above are represented in reviewed project guidance and verified by tests.

