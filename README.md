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

# Replay ordered durable lifecycle events. Use -N so curl does not buffer SSE.
curl -NsS http://127.0.0.1:8000/v1/tasks/<task_id>/events
```

The worker performs bounded search and fetch passes, then asks the configured local LLM for
an evidence-coverage decision. Incomplete coverage schedules focused secondary queries ahead of
unused planned queries, while source, iteration, elapsed-time, and model-output-token budgets
bound the loop. Cancellation is checked before and after every model, search, and fetch boundary;
canonical URLs are not fetched twice within an attempt. Retained page text is placed in an
explicitly delimited untrusted-data block and is never treated as model instructions.

After evaluation, the model returns structured candidate claims. Rancho treats that response as
untrusted: it retains only bounded claims whose evidence UUIDs belong to the task and whose URLs
match retained evidence. The final result renders citations from canonical stored URLs in the form
`[evidence:<uuid>](<canonical-url>)`. The task becomes `completed` only after those checks and
claim persistence succeed. Missing evidence, an unavailable model, malformed output, or no
verified claims produces an honest `partial` result with a redacted terminal event.

The task status response includes `evidence_count`, `claim_count`, and `result`. A positive claim
count is auditable through the UUIDs embedded in the canonical citations; unsupported generated
claims never appear in the result or durable claim table.

To reconnect after an event, replay only newer events with its SSE ID:

```sh
curl -NsS http://127.0.0.1:8000/v1/tasks/<task_id>/events \
  -H 'Last-Event-ID: 3'
```

Request cancellation or retry a partial task (up to three attempts):

```sh
curl -sS -X POST http://127.0.0.1:8000/v1/tasks/<task_id>/cancel
curl -sS -X POST http://127.0.0.1:8000/v1/tasks/<task_id>/retry
```

For a local end-to-end verification, configure `RANCHO_LLM_PROVIDER`,
`RANCHO_LLM_BASE_URL`, and `RANCHO_LLM_MODEL`, submit a task, wait for a terminal event, then
inspect the status response. Every URL in `result` must also be present as a canonical URL in the
task's retained evidence, and `completed` must have a positive `claim_count`.

The loop budgets are configured with `RANCHO_RESEARCH_MAX_ITERATIONS`,
`RANCHO_RESEARCH_MAX_ELAPSED_SECONDS`, `RANCHO_RESEARCH_MAX_PLANNER_TOKENS`, and
`RANCHO_RESEARCH_MAX_MODEL_TOKENS`. `RANCHO_RESEARCH_PLANNING=true` enables an initial planning
pass; iterative evidence evaluation remains bounded by the same limits.

## FindAll candidate discovery

`POST /v1/findall` starts a bounded Phase 3 discovery task. The declared schema supports 1–20
named fields of type `string`, `number`, or `boolean`; unknown request fields and unsupported
schema types are rejected. FindAll uses the same durable queue, safe fetcher, cancellation,
budgets, events, and retry controls as research tasks, while persisting results separately as
schema-valid candidates linked to retained evidence UUIDs.

```sh
curl -sS -X POST http://127.0.0.1:8000/v1/findall \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: california-ev-companies' \
  -d '{
    "objective":"Find electric vehicle companies in California",
    "output_schema":{"name":"string","active":"boolean"},
    "max_sources":10
  }'

curl -sS http://127.0.0.1:8000/v1/tasks/<task_id>
```

The task response identifies `task_type: "findall"` and returns `candidates`; each candidate
contains only the declared fields plus its retained `evidence_ids`. Model prose, unknown fields,
wrong types, and candidates without task-owned evidence are omitted rather than persisted.

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
| Service hostnames | `rancho`, `worker`, `searxng`, `postgres`, `redis` (private Compose network) |
| Published port | Only `rancho` → host `${RANCHO_HOST_PORT:-8000}`; SearXNG, Postgres, and Redis are not published |
| Public base URL | `RANCHO_PUBLIC_BASE_URL` (front this service with your own TLS terminator) |
| Auth mode | No inbound auth in this stack; SearXNG and the LLM are trusted internal services reached by service name. Optional `RANCHO_SEARCH_API_KEY` / `RANCHO_LLM_API_KEY` are sent only as outbound bearer tokens |
| Secret/token source | Git-ignored `.env` (`SEARXNG_SECRET`, `POSTGRES_PASSWORD`, optional API keys); never committed and never baked into images |
| Persistent volume | `rancho-pgdata` holds PostgreSQL data; Redis is ephemeral |

`/ready` still verifies live SearXNG reachability, so a started-but-unhealthy provider yields the
redacted `provider_unavailable` response rather than a false ready signal.
