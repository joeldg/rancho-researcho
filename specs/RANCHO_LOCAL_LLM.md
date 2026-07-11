# Rancho Local LLM Client Contract

## Scope

This project-scoped contract governs the Phase 1 OpenAI-compatible local LLM client for Ollama
and vLLM, including configuration, model policy, bounded retries, fallback, redaction, and tests.

## Intent

Rancho must use explicitly configured local model infrastructure without silently sending prompts
or evidence to an unintended provider, leaking credentials, or inventing a model response after
an overload or timeout.

## Requirements

1. `RANCHO_LLM_PROVIDER` is `ollama` or `vllm`; `RANCHO_LLM_BASE_URL` and
   `RANCHO_LLM_MODEL` are administrator-controlled configuration. The provider endpoint may be
   private or loopback only as trusted internal control-plane infrastructure; request payloads,
   search results, and web content cannot alter its host, scheme, port, path, or headers.
2. The client uses the OpenAI-compatible `POST /v1/chat/completions` path and sends only a bounded
   request containing model, messages, temperature, and maximum output tokens. It validates that
   a successful response has a non-empty assistant message before returning it.
3. `RANCHO_LLM_API_KEY` is secret material. It is sent only in the configured authorization
   header and must not appear in API responses, exceptions, metrics, event payloads, logs, tests,
   or persisted task/evidence/claim records.
4. A model request uses a connect timeout of at most three seconds and a read timeout of at most
   sixty seconds. It makes at most three total attempts with exponential backoff and bounded
   jitter for connection errors, timeouts, and status 408, 429, 500, 502, 503, or 504. It does not
   retry validation errors, authentication failures, or malformed responses.
5. `RANCHO_LLM_COMPLEX_MODEL` is optional. The internal model policy uses the default model for
   bounded/simple operations and the complex model only for an approved internal high-effort
   classification; callers cannot select an arbitrary model. If the complex model is unavailable,
   a retryable failure may fall back once to the default model. No fallback is attempted without a
   configured default model.
6. A timeout, retry exhaustion, overload, out-of-memory/availability signal, malformed response,
   or unsupported provider raises a typed unavailable error. Callers return an explicit unavailable
   or partial state; they never synthesize an LLM answer, claim, citation, or completion status.
7. The client records only redacted operational fields: configured provider name, configured model
   name, attempt count, duration, outcome category, and token counts if returned by the provider.
   It does not record raw prompts, raw completions, API keys, or provider error bodies by default.
8. Tests use `httpx.MockTransport` or a controlled local server and cover valid responses,
   malformed responses, retryable and non-retryable failures, retry bounds, complex-model fallback,
   model-selection policy, and secret redaction. They make no live model request.

## Non-Goals

This contract does not define prompt templates, prompt-injection defense, claim verification,
streaming completions, model serving, GPU scheduling, or provider-specific administration.

## Acceptance Evidence

- A controlled fixture verifies fixed-path requests, model policy, bounded retry, and fallback.
- A failure fixture proves no raw provider body or API key reaches the public error or logs.
- Tests show an unavailable model results in an explicit unavailable/partial result, not invented
  text or a fabricated citation.
- Code trace mappings connect client, configuration, model policy, and tests to this contract.

## Token Budget Class

Project contract.

## Related Specs

- `RANCHO_API_SECURITY.md`
- `RANCHO_PROJECT_PROFILE.md`
- `GLOBAL_SECURITY.md`
- `SECURITY_AND_SECRETS.md`
- `TRACEABILITY_AND_OBSERVABILITY.md`

## AI Agent Directives

Implement only the bounded OpenAI-compatible client after this contract is reviewed and
published. Do not add a cloud-provider fallback, expose provider errors, or allow caller-controlled
provider/model routing.

