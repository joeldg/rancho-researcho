# Rancho Researcho Project Profile

## Scope

This project-scoped profile records the repository-specific product, runtime, and deployment
choices for `github.com/joeldg/rancho-researcho`.

## Intent

Rancho Researcho is an evidence-first, self-hosted research API. Its first consumer is Parkour,
which needs a predictable HTTPS search endpoint and explicit unavailable states rather than
fabricated research results.

## Requirements

1. The project type is `SaaS Backend API`; the initial delivery is a Python 3.9+ FastAPI
   service with typed request/response models and contract tests.
2. The Phase 1 public contract is `POST /v1/search`, with `/search` as a compatibility alias.
   Successful results retain a source URL, title, bounded excerpt, source ID, and retrieval time.
3. SearXNG is the first supported search provider. It runs as trusted internal infrastructure,
   commonly on a Compose/private network or loopback endpoint, and is selected solely through
   administrator-controlled `RANCHO_SEARCH_PROVIDER` and `RANCHO_SEARCH_BASE_URL` settings.
4. Rancho's public endpoint must use HTTPS in production. The internal SearXNG control-plane
   endpoint is not exposed by the public API and must not be derived from caller input, search
   results, crawled links, or web content.
5. Local LLMs and search engines are configuration-selected components. Their credentials remain
   in environment or secret-manager inputs and are never returned by API, metrics, logs, or
   stored task results.
6. PostgreSQL, Redis, durable tasks, URL extraction, crawling, deep research, FindAll, and
   monitoring are later milestones. The SearXNG slice does not fetch result URLs.
7. Contract tests cover health, readiness, metrics, input validation, unavailable-provider
   behavior, successful normalized SearXNG results, and the control-plane/untrusted URL boundary.

## Non-Goals

This profile does not define production authentication policy, worker queues, browser automation,
database schemas, generic outbound proxying, or the full research loop.

## Acceptance Evidence

- A configured SearXNG fixture returns bounded, deduplicated results at `/v1/search`.
- A missing or failed provider returns 503 `provider_unavailable` without fabricated results.
- Tests prove caller-controlled URLs cannot redirect the SearXNG adapter to private services.
- Deployment documentation distinguishes the public HTTPS API from the trusted internal provider.

## Token Budget Class

Project contract.

## Related Specs

- `RANCHO_API_SECURITY.md`
- `PROJECT_DESCRIPTION.md`
- `GLOBAL_SECURITY.md`
- `CODING_STANDARDS.md`
- `SECURITY_AND_SECRETS.md`

## AI Agent Directives

Treat SearXNG as a configuration-controlled provider, never as an arbitrary URL proxy. Keep
untrusted result/extraction URLs on the separate validation path defined by the API security
contract.

