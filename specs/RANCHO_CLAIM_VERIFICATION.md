# Rancho Claim Verification and Citation Contract

## Scope

Governs synthesis, claim extraction, evidence linkage, and citation rendering for retained research evidence.

## Requirements

1. Final synthesis and claims use only retained evidence belonging to the task; no URL may appear in output unless it matches stored evidence.
2. Each persisted claim references one or more evidence UUIDs and records bounded claim text. Claims without support are omitted, never marked verified.
3. LLM output is treated as untrusted candidate text. The verifier validates evidence IDs, task ownership, and citation URLs before persistence or presentation.
4. Citations render from canonical stored URLs and identify the linked evidence. Provider errors, secrets, and raw internal exceptions never appear in claims, results, logs, or SSE payloads.
5. A task becomes `completed` only when its final result contains no unsupported claims. If verification is unavailable or incomplete, it ends `partial` with a redacted event.

## Acceptance Evidence

- Tests reject unknown/cross-task evidence IDs and URL citations absent from evidence.
- Tests prove unsupported generated claims are omitted and verified claims remain auditable.

## Non-Goals

Truth adjudication beyond retained evidence, legal/medical advice, and external citation databases.
