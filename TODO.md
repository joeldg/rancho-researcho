# Rancho Researcho - Development TODO & Phases

This document outlines the development phases, technical hurdles, and step-by-step tasks required to implement Rancho Researcho as an autonomous, self-hosted web-research agent using a local LLM.

---

## Phase 1: Foundation & Compatibility MVP (Fast Search & Direct Scrape)

Goal: Implement the Parkour-compatible `/v1/search` endpoint using direct local search wrappers, a local LLM integration, and raw web scraping.

### 1.1 Project Setup & Local Infrastructure
- [x] Initialize Python FastAPI project with Poetry/pipenv/uv.
- [ ] Create Docker Compose file with dependencies:
  - [ ] PostgreSQL (for durable task and evidence metadata).
  - [ ] Redis (for task queuing and event storage).
  - [ ] SearXNG (local metasearch engine for private queries).
- [x] Set up basic health, readiness, and metrics routes (`/health`, `/ready`, `/metrics`).
- [x] Configure configuration loader (`pydantic-settings`) reading from `.env`.

### 1.2 Local LLM Client Wrapper
- [ ] Write client wrapper for OpenAI-compatible REST APIs (Ollama/vLLM).
- [ ] Implement query timeout and retry decorator with exponential backoff.
- [ ] Add support for selecting specific local models (e.g., `llama3.1:8b`, `mistral:7b`) based on query complexity.
- [ ] Implement fallbacks for when the local model is overloaded or out of memory.

### 1.3 Raw Search Adapters
- [ ] Implement **DuckDuckGo** raw search adapter (scraping HTML or using direct search libs).
- [x] Implement **SearXNG** JSON API adapter.
- [ ] Implement **Google Custom Search / Bing Search API** adapters as optional developer overrides.
- [ ] Create search orchestrator that executes queries across active adapters, deduplicates URLs, and normalizes result schema.

### 1.4 Web Content Extraction (Scraper)
- [ ] Implement HTTP client for direct URL fetching with:
  - [ ] Enforced outbound SSRF blocker (vetting resolved IPs against private/loopback subnets).
  - [ ] User-agent rotation, timeout limits, and content-length cap.
  - [ ] Redirect loop detection.
- [ ] Implement HTML-to-Markdown parser (using `BeautifulSoup` + `markdownify`) that:
  - [ ] Drops scripts, styles, forms, navigation headers, footers, and sidebars.
  - [ ] Preserves links, tables, and headers to retain context for the LLM.

### 1.5 Compatibility API (`POST /v1/search`)
- [x] Implement the `POST /v1/search` endpoint conforming to the Parkour API spec.
- [ ] Implement a fast LLM-driven snippet generator: extract a context-relevant excerpt from scraped page markdown for the requested query.
- [x] Ensure 503 error handling returning `provider_unavailable` when LLM/Search is offline.

---

## Phase 2: Asynchronous Job Engine & Deep Research Orchestration

Goal: Establish the worker queue, database schemas, stateful agent research loop, and claim verification.

### 2.1 Database & Background Worker
- [ ] Create database tables and migrations (using Alembic/SQLAlchemy):
  - [ ] `ResearchTask` (tracks task metadata, state, input query, models used).
  - [ ] `Evidence` (stores canonical URLs, scraped markdown content, and hash).
  - [ ] `Claim` (contains extracted claims and links to source evidence).
- [ ] Integrate background worker queue (e.g., using `arq`, `Celery`, or `rq`) running on Redis.

### 2.2 Deep Research Agent Loop
- [ ] Implement the stateful **Research Loop** driven by the local LLM:
  1. **Planning**: LLM expands the objective into an initial list of target search queries.
  2. **Search & Crawl**: Execute queries and fetch top result URLs.
  3. **Read**: Scrape text content of the target URLs.
  4. **Evaluate**: LLM reviews retrieved evidence against the goal, determining which questions remain unanswered.
  5. **Iterate**: Generate secondary queries or target specific sub-links to crawl (up to max recursion depth or budget limit).
  6. **Synthesize**: Compile the final answer markdown.

### 2.3 Evidence & Citation Engine
- [ ] Implement a post-processing claim extractor:
  - [ ] LLM identifies distinct facts/claims in the generated synthesis.
  - [ ] Validate that every claim is backed by at least one excerpt from the retrieved `Evidence`.
  - [ ] Insert claim-level citations and output normalized structured data models.
- [ ] Ensure the final synthesis cannot cite any URL absent from the `Evidence` store.

### 2.4 Server-Sent Events (SSE) Streaming
- [ ] Create SSE endpoint `GET /v1/tasks/{task_id}/events` supporting connection recovery (`Last-Event-ID`).
- [ ] Emit granular events during execution: `task.created`, `search.completed`, `evidence.extracted`, `claim.verified`, `progress`, and terminal states.

---

## Phase 3: Advanced Agent Capabilities (FindAll & Monitors)

Goal: Implement structured candidate extraction and scheduled tracking monitors.

### 3.1 FindAll Candidate Discovery Engine
- [ ] Implement `POST /v1/findall` endpoint for discovery runs (e.g., "Find all electric vehicle startups in California").
- [ ] Implement the FindAll pipeline:
  - [ ] LLM generates targeted candidate-finding queries.
  - [ ] Extract potential candidate entities from search results and crawled pages.
  - [ ] For each candidate, run a sub-agent pass using LLM to extract fields matching a JSON/Pydantic schema.
  - [ ] Record match status, reasoning, and evidence IDs for each candidate.

### 3.2 Recurring Monitor Scheduler
- [ ] Implement scheduler (e.g., APScheduler) to run periodic monitoring jobs.
- [ ] Implement `POST /v1/monitors` endpoint.
- [ ] Implement change detection engine:
  - [ ] Compare current search result hashes / text semantic structures with the previous run.
  - [ ] Trigger an alert webhook if material changes are detected.
  - [ ] Optionally trigger a follow-up deep research task with budget bounds.

---

## Phase 4: Production Hardening, Safety, & Optimization

Goal: Secure, optimize, and scale the local agent for production workloads.

### 4.1 Caching & Efficiency
- [ ] Implement local HTTP page cache (Redis/DB) based on URL canonicalization and content hash.
- [ ] Cache LLM embeddings or classification results to avoid redundant model passes during a deep crawl.

### 4.2 Security & Hostile Input Defenses
- [ ] Harden the system against **Prompt Injection** contained in web sources:
  - [ ] Use XML tag isolation and explicit system/user formatting.
  - [ ] Use a secondary LLM verification pass to detect instructions leaked in scraped text.
- [ ] Ensure full containment of outbound HTTP requests (SSRF validation at DNS resolution and socket connection level).

### 4.3 Reliability & Resilience
- [ ] Implement circuit breakers for local LLM requests to prevent CPU/OOM locking under heavy load.
- [ ] Add rate-limiting policies per tenant and token allocation caps.
- [ ] Signed webhooks (HMAC-SHA256 signature verification) for callback security.

### 4.4 Observability
- [ ] Add detailed OpenTelemetry tracing for the entire research pipeline.
- [ ] Report model token consumption, crawling byte count, search engine query counts, and queue wait times in Prometheus format.
