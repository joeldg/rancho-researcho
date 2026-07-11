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
