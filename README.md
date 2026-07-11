# Rancho Researcho

Rancho Researcho is an autonomous, self-hosted web-research agent. It exposes a Parkour-compatible `/v1/search` endpoint and richer APIs for deep research, extraction, crawling, asynchronous tasks, FindAll-style entity discovery, and recurring monitors, powered internally by a local LLM and self-contained search/extraction modules.

The detailed project specification is in
[PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md). It defines the core agent components, the normalized contract, streaming events, security policy, anti-hallucination requirements, configuration, milestones, and acceptance criteria.

## Current capability

The Phase 1 compatibility foundation is available now:

- `POST /v1/search` and `/search` accept bounded Parkour-compatible search requests.
- A configured, trusted internal SearXNG provider supplies normalized, deduplicated results.
- `/health`, `/ready`, and `/metrics` expose process and provider state without secrets.
- An unconfigured or failed provider returns a redacted HTTP 503 `provider_unavailable` response;
  Rancho never invents search results.
- The local Ollama/vLLM client uses a fixed OpenAI-compatible completion endpoint, bounded retries,
  internally selected models, and typed unavailable failures. It is available for later synthesis
  stages but is not yet part of the synchronous search response.

DuckDuckGo, local LLM synthesis, extraction/crawling, and asynchronous research tasks are still
in development. See [TODO.md](TODO.md) for the current delivery checklist.

## Local development

The initial scaffold deliberately exposes an honest unavailable-provider response until a
search adapter is configured and implemented. It never fabricates web results.

```sh
uv sync --all-groups
uv run pytest
uv run uvicorn rancho.main:app --reload
```

Copy `.env.example` to `.env` to configure local services. Do not commit `.env` or API keys.

`RANCHO_PUBLIC_BASE_URL` is the public HTTPS address of Rancho. In contrast,
`RANCHO_SEARCH_BASE_URL` is a trusted internal SearXNG control-plane address (for example,
`http://searxng:8080` in Docker Compose). It is configured by the operator and is never derived
from a caller request or search result.

## Try the async task flow

Start the local stack and apply its durable-schema migration before creating a research task:

```sh
docker compose up -d --build
docker compose exec rancho alembic upgrade head

# The response contains a task_id. Substitute it in the status request below.
curl -sS -X POST http://127.0.0.1:8000/v1/research \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-1' \
  -d '{"objective":"Compare solid-state battery approaches","max_sources":5}'

curl -sS http://127.0.0.1:8000/v1/tasks/<task_id>
```

The current worker intentionally ends the task as `partial` after recording `task.created` and
`stage.started`; the full deep-research loop is the next delivery slice. Paste both JSON responses
here and I can verify the durable lifecycle is working.

## Running with Docker Compose

The [`docker-compose.yml`](docker-compose.yml) stack runs the API together with its trusted
internal dependencies, so `/v1/search` works end to end. It conforms to
[`specs/RANCHO_DEPLOYMENT.md`](specs/RANCHO_DEPLOYMENT.md).

```sh
cp .env.example .env
# Set at least SEARXNG_SECRET (openssl rand -hex 32) and POSTGRES_PASSWORD.
docker compose up --build
curl -s localhost:8000/ready
curl -s -X POST localhost:8000/v1/search -H 'content-type: application/json' \
  -d '{"query":"self-hosted search","max_results":5}'
```

Deployment facts (per `SECURITY_AND_SECRETS.md` requirement 7):

| Field | Value |
| --- | --- |
| Service hostnames | `rancho`, `searxng`, `postgres`, `redis` (private Compose network) |
| Published port | Only `rancho` → host `${RANCHO_HOST_PORT:-8000}`; SearXNG, Postgres, and Redis are not published |
| Public base URL | `RANCHO_PUBLIC_BASE_URL` (front this service with your own TLS terminator) |
| Auth mode | No inbound auth in this stack; SearXNG and the LLM are trusted internal services reached by service name. Optional `RANCHO_SEARCH_API_KEY` / `RANCHO_LLM_API_KEY` are sent only as outbound bearer tokens |
| Secret/token source | Git-ignored `.env` (`SEARXNG_SECRET`, `POSTGRES_PASSWORD`, optional API keys); never committed and never baked into images |
| Persistent volume | `rancho-pgdata` holds PostgreSQL data; Redis is ephemeral |

`/ready` still verifies live SearXNG reachability, so a started-but-unhealthy provider yields the
redacted `provider_unavailable` response rather than a false ready signal.
