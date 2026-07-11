# Rancho Researcho

Rancho Researcho is an autonomous, self-hosted web-research agent. It exposes a Parkour-compatible `/v1/search` endpoint and richer APIs for deep research, extraction, crawling, asynchronous tasks, FindAll-style entity discovery, and recurring monitors, powered internally by a local LLM and self-contained search/extraction modules.

The detailed project specification is in
[PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md). It defines the core agent components, the normalized contract, streaming events, security policy, anti-hallucination requirements, configuration, milestones, and acceptance criteria.

## Local development

The initial scaffold deliberately exposes an honest unavailable-provider response until a
search adapter is configured and implemented. It never fabricates web results.

```sh
uv sync --all-groups
uv run pytest
uv run uvicorn rancho.main:app --reload
```

Copy `.env.example` to `.env` to configure local services. Do not commit `.env` or API keys.
