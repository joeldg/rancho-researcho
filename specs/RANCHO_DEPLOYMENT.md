# Rancho Deployment and Container Infrastructure Contract

## Scope

This project-scoped contract governs the Docker and Compose deployment of the Rancho API and
its trusted internal dependencies (SearXNG, PostgreSQL, Redis): service topology, network
exposure, health gating, persistence, image construction, and configuration wiring. It narrows
`SECURITY_AND_SECRETS.md` and `RANCHO_API_SECURITY.md` for this deployment surface.

## Intent

Rancho must be runnable as a reproducible, self-hosted stack in which the search dependency is
reachable only as trusted internal infrastructure, no secrets are baked into images or source,
and the API never reports ready until its provider is actually serving.

## Requirements

1. A single Compose stack defines four services: `rancho` (the API), `searxng`, `postgres`, and
   `redis`. Services communicate over a private Compose network. Only the `rancho` API port is
   published to the host; `searxng`, `postgres`, and `redis` expose no host port mappings by
   default.
2. The API receives `RANCHO_SEARCH_BASE_URL` pointing at the internal service address
   `http://searxng:8080` as operator configuration. It is never derived from a caller request or
   a search result, consistent with `RANCHO_API_SECURITY.md` provider configuration.
3. SearXNG is configured to enable the JSON response format that `SearxngSearchAdapter` requires
   (`search.formats` includes `json`). Its `secret_key` is supplied from the environment and is
   never committed.
4. PostgreSQL uses a named, persistent volume so durable Phase 2 task and evidence data survive
   container restarts. Redis is treated as ephemeral transient state and must not be relied on as
   a durable record, consistent with `RANCHO_ASYNC_RESEARCH.md`.
5. All secrets (SearXNG secret key, PostgreSQL password, and any provider or LLM API keys) are
   injected through environment or a git-ignored `.env`. Committed Compose files, the Dockerfile,
   and service configuration contain only non-secret placeholders. This narrows
   `SECURITY_AND_SECRETS.md` requirements 1 and 7 to this stack.
6. The API image is built reproducibly from a pinned base image and locked dependencies, runs as a
   non-root user, and contains no secrets and no `.env` file.
7. Compose declares dependency ordering and healthchecks so `rancho` starts only after `searxng`,
   `postgres`, and `redis` report healthy. Container start does not by itself mean ready: `/ready`
   still gates on live provider reachability per `RANCHO_API_SECURITY.md`.
8. Deployment documentation records, for this stack, the fields required by
   `SECURITY_AND_SECRETS.md` requirement 7: service hostnames, published port(s), public base URL,
   auth mode, secret/token source path, and the persistent database volume.

## Non-Goals

This contract does not define production orchestration (Kubernetes or Swarm), TLS termination or
reverse-proxy specifics, autoscaling, backup and restore procedures, or the Phase 2 database
schema, which `RANCHO_ASYNC_RESEARCH.md` governs.

## Acceptance Evidence

- `docker compose config` validates and shows only the API port published; `searxng`, `postgres`,
  and `redis` have no host port mappings.
- A scan of committed files shows no secret values in Compose files, the Dockerfile, or SearXNG
  settings; only `.env.example` placeholders exist.
- With the stack up, `/ready` returns ready only when SearXNG answers a bounded JSON query,
  `/v1/search` returns normalized results, and a stopped SearXNG yields the redacted HTTP 503
  `provider_unavailable` response.
- README documents the `SECURITY_AND_SECRETS.md` requirement 7 fields for the stack.

## Token Budget Class

Project contract.

## Related Specs

- `RANCHO_API_SECURITY.md`
- `SECURITY_AND_SECRETS.md`
- `GLOBAL_SECURITY.md`
- `RANCHO_ASYNC_RESEARCH.md`
- `RANCHO_PROJECT_PROFILE.md`

## AI Agent Directives

Implement the Compose stack and Dockerfile only after this contract is reviewed and published.
Never publish provider, database, or search ports to the host beyond the API port, never commit
secrets or a real `.env`, and never weaken `/ready` to report readiness without live provider
verification.
