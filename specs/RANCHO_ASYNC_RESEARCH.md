# Rancho Asynchronous Research, Persistence, and Event Contract

## Scope

This project-scoped contract governs Phase 2 task creation, durable lifecycle state, evidence and
claim persistence, PostgreSQL migrations, Redis-backed worker execution, and SSE event replay.

## Intent

Long-running research must be observable, cancellable, retryable, and recoverable without
pretending that work completed. Every persisted claim must remain traceable to retained evidence.

## Requirements

### Architecture and storage

1. Phase 2 uses PostgreSQL as the durable system of record, SQLAlchemy 2 asynchronous models,
   and Alembic migrations. A migration is immutable after release; schema changes require a
   forward migration and an upgrade/downgrade test.
2. Redis and `arq` provide background execution and transient event fan-out. Redis is not the
   sole record of a task's terminal state, evidence, claims, or cancellation request.
3. PostgreSQL stores `research_tasks`, `evidence`, `claims`, and `task_events`. All primary keys
   are UUIDs; timestamps are UTC; enums are explicit; foreign keys, unique constraints, and
   indexes support task status and evidence/claim lookup. A task event has a task UUID, monotonic
   sequence number, UTC timestamp, type, stage, and redacted JSON payload.
4. Evidence stores its canonical URL, original URL, title, bounded excerpt/content, retrieval
   time, SHA-256 content hash, and source metadata. A claim references one or more evidence UUIDs;
   a final result must not refer to a URL absent from task evidence.

### Task lifecycle and worker behavior

5. `POST /v1/research` validates a bounded objective and budget, creates a `queued` task in the
   same transaction as its initial `task.created` event, enqueues it after commit, and returns
   HTTP 202 with `task_id`, `status`, and a status URL. It supports an `Idempotency-Key` header:
   the same key and equivalent request return the original task; a different request returns 409.
6. Task states are `queued`, `running`, `partial`, `completed`, `failed`, `cancel_requested`, and
   `cancelled`. Terminal states are `partial`, `completed`, `failed`, and `cancelled`. Workers
   claim only queued/retryable tasks, emit `stage.started` before work, and record terminal state
   plus terminal event in one durable transaction.
7. `POST /v1/tasks/{task_id}/cancel` is idempotent. It changes an active task to
   `cancel_requested`, emits an event, and returns the current state. Workers check cancellation
   between bounded stages and finish as `cancelled`; cancellation never deletes evidence already
   retained for the task.
8. `POST /v1/tasks/{task_id}/retry` accepts only `failed` or `partial` tasks with a retryable
   stage, creates a new execution attempt, and leaves prior events/evidence auditable. The initial
   policy permits at most three attempts per task unless a later approved budget policy narrows it.

### SSE and events

9. `GET /v1/tasks/{task_id}/events` streams `text/event-stream` events named `task.created`,
   `stage.started`, `search.completed`, `evidence.extracted`, `claim.verified`, `progress`,
   `task.partial`, `task.completed`, `task.failed`, and `task.cancelled`. Each event includes an
   SSE ID equal to the task sequence and a JSON payload containing task ID, sequence, timestamp,
   stage, and redacted data.
10. `Last-Event-ID` replays all retained events after that sequence before live delivery. A
    missing or expired sequence produces a deterministic 410 event-history-expired response;
    duplicate delivery is allowed, so event consumers must be idempotent. Terminal events remain
    replayable for at least 24 hours.

### Security, observability, and tests

11. Objectives, source content, provider errors, and event payloads are treated as sensitive
   tenant data. Logs, metrics, and SSE payloads must not expose API keys, provider credentials,
   raw secret-bearing configuration, or unredacted internal exceptions.
12. Contract tests use disposable PostgreSQL/Redis fixtures or controlled fakes. They cover
   idempotent creation, invalid transitions, cancellation, retry bounds, durable event ordering,
   Last-Event-ID replay/expiry, and evidence-to-claim referential integrity. Migration tests run
   Alembic upgrade and downgrade against an empty database.

## Non-Goals

This contract does not define the local LLM planning/evaluation algorithm, page extraction,
production tenant authentication, webhooks, monitors, or a distributed workflow engine beyond
the stated `arq` worker boundary.

## Acceptance Evidence

- An integration test creates a task, observes ordered SSE events, cancels it, and replays its
  terminal event after reconnecting.
- A migration test creates all durable tables and proves constraints reject invalid state/event
  records.
- A retry test retains earlier execution evidence and does not exceed the attempt limit.
- A traceability report maps public routes, schemas, migrations, workers, and event handlers to
  the exact sections of this contract.

## Token Budget Class

Project contract.

## Related Specs

- `RANCHO_API_SECURITY.md`
- `RANCHO_PROJECT_PROFILE.md`
- `GLOBAL_SECURITY.md`
- `IMPLEMENTATION_EVIDENCE.md`
- `TRACEABILITY_AND_OBSERVABILITY.md`

## AI Agent Directives

Do not implement the Phase 2 database, worker, or SSE surface until this contract is reviewed
and published. Do not treat Redis as durable truth, omit terminal events, or add a claim without
evidence links.

