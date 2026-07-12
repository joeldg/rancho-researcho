# Rancho Deep Research Loop Contract

## Scope

Governs bounded LLM planning, iterative search/fetch evaluation, cancellation checks, and honest terminal outcomes for a Phase 2 research task.

## Requirements

1. A task has explicit source, iteration, elapsed-time, and model-token budgets. It stops before any budget is exceeded.
2. Planning and evaluation use only the configured local LLM client. Prompts isolate retained page content as untrusted delimited data; page text is never executed as instructions.
3. Each iteration records a durable redacted `progress` event and uses only the approved search and SSRF-contained fetch boundaries. Duplicate canonical URLs are not fetched twice in an attempt.
4. The worker checks durable cancellation before and after every model, search, and fetch stage. Cancellation retains already persisted evidence and ends with `task.cancelled`.
5. Provider or model unavailability produces a redacted partial or failed terminal state; the worker never invents research, evidence, claims, citations, or completion.
6. A completed task requires a final synthesis accepted by the claim-verification contract. Otherwise it is partial.

## Acceptance Evidence

- Controlled tests cover budget stops, cancellation between stages, duplicate URL avoidance, model failure, and ordered events.
- Integration test proves a bounded multi-step task retains only safely fetched evidence.

## Non-Goals

Claim validation, FindAll, monitors, external model providers, and browser automation.
