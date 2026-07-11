# Rancho Researcho

## Project description

Rancho Researcho is an autonomous, self-hosted web-research agent. It gives Parkour a small, predictable HTTPS endpoint for search and deep research, executing all search queries, web crawling, content extraction, and synthesis internally using a local LLM rather than delegating to external commercial research APIs. Its job is not merely to return links: it should plan its research, gather evidence, preserve the provenance of every claim, expose progress, and make uncertainty and partial failure visible to the caller.

The first integration target is nvidiarouter/Parkour. Parkour sends a bounded search request and expects a JSON object containing a `results` array. Rancho must therefore expose a compatibility endpoint that is simple enough for that contract, while also offering richer asynchronous research APIs for clients that can use them.

## Why this project exists

Language models hallucinate when they answer current or obscure questions from memory. A useful research service must separate retrieval from synthesis and must make it difficult to produce an answer that cannot be traced to retrieved evidence. Rancho should provide:

- fast search for grounding a single model turn using direct, self-hosted search engine queries;
- deep, multi-step research orchestrated by a local LLM;
- URL extraction and bounded crawling;
- structured “find all matching entities” jobs;
- recurring monitors for changes and alerts;
- streaming progress and webhooks for long-running jobs;
- one normalized evidence and citation model independent of any external service;
- budgets, cancellation, retries, rate limits, and complete observability.

## Capability model

Rancho models capabilities rather than external vendors. The internal agent orchestrator implements these capabilities using configured local components:

| Capability | Meaning |
| --- | --- |
| `search` | Return ranked web results and bounded excerpts in one request via raw search query. |
| `extract` | Turn one or more public URLs into clean, citation-ready markdown content. |
| `crawl` | Discover and extract linked pages under explicit depth and page limits. |
| `research` | Plan searches, read sources, cross-check evidence, and synthesize an answer using local LLM loops. |
| `task` | Run custom structured research asynchronously with a schema and processor/effort. |
| `findall` | Discover candidates matching natural-language criteria and optionally enrich them. |
| `monitor` | Re-run a query on a schedule and emit material changes. |
| `stream` | Emit progress, source, citation, and completion events over SSE or webhooks. |

Component selection and search behaviors should be policy-driven. A request can specify preferred parameters (e.g. depth, effort, specific search engine adapter, model parameters), but the gateway may fall back according to local policy. Every response must state which search adapter and LLM model were actually used.

## Core Agent Components

### Local LLM Engine

The brains of the agent are driven by a local LLM runner (e.g., Ollama or vLLM) exposed via an OpenAI-compatible REST API. The LLM is invoked for several specialized tasks in the pipeline:
- **Planning & Query Expansion:** Translating a high-level research prompt into one or more precise, keyword-targeted search queries.
- **Evaluation & Relevancy Filtering:** Reviewing extracted page content to filter out noise and extract key facts relative to the research goal.
- **Claim Verification:** Isolating specific factual claims made in the synthesized text and linking them back to the source ID in the evidence database.
- **Synthesis:** Writing the final markdown report based strictly on the retrieved evidence, ensuring no hallucinations.

### Search Adapter Interface

Rather than using third-party research APIs, Rancho implements direct adapters for raw search engines. The adapter layer abstracts query syntax and result normalization for:
- **SearXNG:** A self-hosted metasearch engine that acts as the primary option for fully private, localized searches.
- **DuckDuckGo:** A lightweight, no-auth HTML parser/API for basic web searches.
- **Google Custom Search / Bing Search APIs:** Direct developer API integrations for high-reliability search results when configured.

Rancho executes the search queries, merges results, deduplicates URLs, and extracts initial search snippets.

### Extraction & Bounded Crawling Engine

An internal crawling and scraping component handles URL resolution and content parsing:
- **Scraper:** Fetches raw HTML and converts it to clean, readable Markdown (stripping navigation menus, ads, footer links, and scripts).
- **Crawler:** A bounded queue that discovers and crawls linked pages within the allowed domain or context, matching maximum depth and page count limits.
- **Safety & Isolation:** Outbound requests are subject to strict SSRF protection (preventing link-local and private network requests), timeout controls, response size limits, and `robots.txt` compliance.

### Agent Task Orchestrator (Task & FindAll)

For complex, multi-step, and asynchronous operations, an internal task queue manages agent execution:
- **Deep Research Loop:** A stateful agent loop where the local LLM reviews current findings, formulates follow-up queries, scrapes new links, and continues until the goal is met or the budget is exhausted.
- **FindAll Engine:** A specialized worker that discovers candidates matching natural language criteria, verifies their match status, and extracts structured fields matching a Pydantic schema using the local LLM.
- **Monitor Scheduler:** A cron-based runner that executes scheduled search queries, checks for delta changes in results, and optionally triggers follow-up deep research tasks.

## Parkour compatibility endpoint

Expose `POST /v1/search` (and an alias `POST /search`) with this minimum contract:

```json
{
  "query": "latest developments in solid-state batteries",
  "max_results": 5
}
```

The response must always be a JSON object, even for errors:

```json
{
  "results": [
    {
      "url": "https://example.org/article",
      "title": "Article title",
      "snippet": "A bounded, evidence-bearing excerpt.",
      "source_id": "src_01",
      "published_at": "2026-07-01T00:00:00Z",
      "retrieved_at": "2026-07-10T19:00:00Z"
    }
  ],
  "provider": "rancho-agent",
  "request_id": "req_...",
  "warnings": []
}
```

`url`, `title`, and `snippet` are the compatibility fields consumed by Parkour. Additional fields are optional and must be bounded. Results must be deduplicated, ranked, and limited to the requested count. If the search engine or local LLM is unavailable, return an explicit 503 with a machine-readable `provider_unavailable` error; never invent results or claim that the internet was searched.

The endpoint must be deployable at a public HTTPS URL because nvidiarouter’s research client rejects localhost, private IPs, non-HTTPS URLs, and unsafe ports. For local development, provide a documented tunnel or staging deployment path.

## Rich API surface

### Synchronous primitives

- `POST /v1/search` — ranked results and excerpts.
- `POST /v1/extract` — extract one or more URLs with byte/page limits.
- `POST /v1/crawl` — bounded discovery plus extraction.

### Asynchronous research

- `POST /v1/research` — create a deep research job; return `202` and `task_id`.
- `GET /v1/tasks/{task_id}` — lifecycle, LLM model, budget, and current counters.
- `GET /v1/tasks/{task_id}/result` — final or partial normalized result.
- `GET /v1/tasks/{task_id}/events` — SSE event stream with `Last-Event-ID` support.
- `POST /v1/tasks/{task_id}/cancel` — idempotent cancellation.
- `POST /v1/tasks/{task_id}/retry` — retry only failed, retryable stages.

### Find all and monitoring

- `POST /v1/findall` — create a candidate-discovery run from objective, entity type, match conditions, limit, and optional enrichment schema.
- `GET /v1/findall/{run_id}` and `/result` — status and candidates.
- `POST /v1/monitors` — create a recurring event or snapshot monitor.
- `GET /v1/monitors/{monitor_id}` — status and last execution.
- `DELETE /v1/monitors/{monitor_id}` — stop future executions.
- `POST /v1/webhooks` — authenticated callback receiver.

Operational endpoints: `/health`, `/ready`, `/metrics`, and a redacted `/v1/engines` capability report.

## Normalized data model

Every internal agent response is converted into these stable objects:

```text
ResearchTask
  id, type, status, created_at, updated_at, engine_type, engine_model
  query/objective, budget, usage, warnings, error

Evidence
  source_id, url, canonical_url, title, excerpt, content, author
  published_at, retrieved_at, content_hash, engine_metadata

Claim
  claim_id, text, evidence_ids[], confidence, qualifiers, as_of

Candidate
  candidate_id, name, url, description, match_status, match_reason
  fields, evidence_ids[], confidence

ResearchResult
  answer, claims[], evidence[], citations[], structured_output
  completeness, limitations, freshness, execution_trace
```

No synthesis may cite a URL that is absent from `evidence`. Preserve the exact retrieval time, source URL, and excerpt used for each important claim. Mark conflicting sources instead of silently averaging them. `partial` is a valid terminal state when a budget or crawler stage failed after useful evidence was collected.

## Research pipeline

1. Validate authentication, tenant policy, query length, requested capability, domains, freshness, and budget.
2. Formulate Search Queries: The local LLM parses the user prompt and generates target keyword searches.
3. Search Execution: Execute searches through configured search adapters (e.g. SearXNG, DuckDuckGo), deduplicating results and canonicalizing URLs.
4. Extract & Crawl: Fetch the top URL candidates, convert HTML to clean markdown, and check for prompt injection or malicious payload patterns. Enforce SSRF, size, timeout, robots, and redirect policies.
5. Evaluate Findings: The local LLM processes the retrieved text. If critical questions remain unanswered and budget permits, the agent loops back to generate new search queries.
6. Synthesize: The local LLM generates a consolidated response using only facts present in the evidence bundle, attaching claim-level citations.
7. Validate: Validate structured outputs against schemas, record execution traces and final resource consumption, and emit results.

## Streaming and events

Use SSE with events such as `task.created`, `stage.started`, `search.completed`, `source.found`, `evidence.extracted`, `claim.verified`, `progress`, `engine.unavailable`, `task.partial`, `task.completed`, and `task.failed`. Events must include `task_id`, monotonic sequence, timestamp, stage, and a redacted payload. Reconnects use `Last-Event-ID`; terminal events remain replayable for a configurable retention period. Webhooks must be signed, idempotent, retry with backoff, and never contain LLM API keys.

## Reliability and anti-hallucination requirements

- Never fabricate a result, citation, status, or search execution.
- Return search and LLM errors and “no evidence found” distinctly.
- Require at least one evidence item for a factual claim; otherwise label it as unverified or omit it.
- Preserve conflicting evidence and state the conflict in the result.
- Bound fan-out, recursion, extraction bytes, task duration, and synthesis size.
- Use exponential backoff with jitter, circuit breakers, and idempotency keys.
- Cache normalized evidence by canonical URL/content hash with freshness policy.
- Support tenant-level concurrency, spend, and engine quotas.

## Security

- Store LLM and search credentials (if any) in a secret manager or environment, never in task payloads, logs, event streams, or persisted results.
- Apply outbound SSRF protection to every fetched URL, including redirects and extracted links; block private/link-local metadata addresses by default.
- Enforce domain allow/block lists, maximum response size, MIME restrictions, decompression limits, and request timeouts.
- Authenticate clients, authorize tenant/task access, sign webhooks, and redact query data according to tenant retention policy.
- Treat web content as hostile input: isolate prompt-injection text from control instructions and label source text as untrusted evidence.

## Configuration

Document a `.env.example` with at least:

```dotenv
RANCHO_ENV=development
RANCHO_PUBLIC_BASE_URL=https://research.example.com
RANCHO_DATABASE_URL=postgresql://...
RANCHO_REDIS_URL=redis://...

# Local LLM Integration (Ollama / vLLM / OpenAI-compatible API)
RANCHO_LLM_PROVIDER=ollama
RANCHO_LLM_BASE_URL=http://localhost:11434/v1
RANCHO_LLM_MODEL=llama3.1:8b
RANCHO_LLM_API_KEY=

# Search Engines (searxng / duckduckgo / google / bing)
RANCHO_SEARCH_PROVIDER=searxng
RANCHO_SEARCH_BASE_URL=http://localhost:8080
RANCHO_SEARCH_API_KEY=

RANCHO_MAX_RESULTS=10
RANCHO_MAX_TASK_SECONDS=900
RANCHO_MAX_CRAWL_PAGES=25
RANCHO_MAX_EVIDENCE_BYTES=2000000
RANCHO_ALLOWED_DOMAINS=
RANCHO_BLOCKED_DOMAINS=
RANCHO_WEBHOOK_SIGNING_SECRET=
```

The nvidiarouter integration then uses:

```dotenv
ENABLE_PARKOUR_RESEARCH=True
PARKOUR_RESEARCH_ENDPOINT=https://research.example.com/v1/search
PARKOUR_RESEARCH_API_KEY=<rancho-client-token>
```

## Suggested implementation

Use FastAPI, Pydantic, an async HTTP client, BeautifulSoup / Playwright for page parsing, PostgreSQL for durable task and evidence metadata, Redis for queues/events, and a worker process for long jobs. Keep components behind small interfaces (`search_adapter`, `html_extractor`, `llm_client`, `research_orchestrator`). Contract tests must run against recorded fixtures so local LLM or engine modifications do not change the Parkour response shape unexpectedly.

## Delivery milestones

1. **Agent MVP:** `/v1/search` compatibility endpoint, local LLM adapter (Ollama/vLLM), DuckDuckGo/SearXNG search adapter, SSRF-safe URL scraping, and Parkour integration test.
2. **Stateful Deep Research:** crawling engine, iteration scheduler, task store, Celery/rq worker, SSE events, cancellation, and citation synthesis.
3. **Agent Capabilities:** FindAll structured extraction and evaluation, Monitor execution engine, and scheduling triggers.
4. **Hardening & Performance:** local caching of scraped pages, rate limiting, signed webhooks, concurrency tuning, and model cost/time attribution.

## Acceptance criteria

- A Parkour request against the public `/v1/search` endpoint returns bounded, real, cited results in the exact `results[].url/title/snippet` shape, generated internally.
- With no search engines or local LLM configured, the service returns an explicit diagnostic; it never claims to have searched the web or invents facts.
- A deep research task can be submitted, monitored by polling or SSE, cancelled, and retrieved after completion or partial failure.
- Every factual answer includes source IDs that resolve to stored evidence.
- FindAll preserves candidate match status, reasons, citations, and enrichments.
- Monitor executions are idempotent and can trigger a bounded follow-up task.
- Search timeouts, HTML parse errors, and model rate limits are visible in metrics and task results, with no secret leakage.
- Contract, security, lifecycle, replay, and budget tests pass in CI.

## Non-goals for the first release

Rancho is not a general browser automation platform, a model-serving gateway, a search-index replacement, or a guarantee that every web claim is true. It is a controlled evidence retrieval and research orchestration agent that makes the available evidence, model behavior, and remaining uncertainty explicit.
