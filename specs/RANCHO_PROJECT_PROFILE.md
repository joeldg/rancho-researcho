# Rancho Researcho Project Profile (Draft)

## Scope

This draft records repository-specific choices for `github.com/joeldg/rancho-researcho`.

## Intent

Rancho Researcho is an evidence-first, self-hosted research API. Its first consumer is
Parkour, which needs a predictable HTTPS search endpoint and explicit partial or unavailable
states instead of fabricated research results.

## Requirements

1. The project type is `SaaS Backend API`; the first delivery is a Python 3.9+ FastAPI service.
2. The Phase 1 public contract is `POST /v1/search`, with `/search` as a compatibility alias.
3. A successful result must retain its source URL, title, bounded excerpt, source ID, and
   retrieval time. The service must not invent results, citations, or search execution.
4. Local LLMs and search engines are configuration-selected components. Credentials remain in
   environment or secret-manager inputs and are never returned by API, metrics, or logs.
5. PostgreSQL, Redis, durable tasks, crawling, and deep research are later milestones, not
   required for the initial compatibility scaffold.
6. Contract tests cover health, readiness, metrics, input validation, and unavailable-provider
   behavior before a search adapter is introduced.

## Non-Goals

This draft does not define worker queues, authentication policy, production deployment,
database schemas, or the full research loop.

## Acceptance Evidence

- The FastAPI application has the stated routes and contract tests.
- With no configured provider, `/v1/search` returns a 503 `provider_unavailable` payload.
- No committed environment file contains secrets.

## Token Budget Class

Project contract.

## Related Specs

- `PROJECT_DESCRIPTION.md`
- `GLOBAL_SECURITY.md`
- `CODING_STANDARDS.md`
- `SECURITY_AND_SECRETS.md`

## AI Agent Directives

Treat this file as a local draft until a human submits and publishes it through SpecRegistry.
Do not use it to override published global specs.

