# Rancho FindAll and Monitor Contract

## Scope

Governs bounded structured candidate discovery and recurring monitor execution after the Phase 2 research loop is complete.

## Requirements

1. FindAll accepts a bounded objective and declared output schema, creates a durable task, and returns only candidates linked to retained evidence.
2. Candidate extraction validates against the requested schema; unknown fields, model prose, and unsupported matches are not persisted as results.
3. Monitor schedules are explicit, bounded, and durable. Each run records its input, evidence hashes, outcome, and next scheduled time.
4. Change detection compares retained canonical URLs and content hashes; alerts trigger only on defined material changes.
5. Webhooks are opt-in, HTTPS-only, signed, timeout-bounded, and never include secrets or unredacted provider errors.

## Acceptance Evidence

- Tests cover schema rejection, evidence-linked candidates, idempotent monitor scheduling, deterministic hash change detection, and signed webhook delivery.

## Non-Goals

Unbounded crawling, user authentication design, billing, and arbitrary third-party automation.
