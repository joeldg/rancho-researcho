"""Bounded OpenAI-compatible client for trusted local LLM infrastructure."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit, urlunsplit

import httpx

from rancho.config import Settings

_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_TIMEOUT = httpx.Timeout(connect=3.0, read=60.0, write=60.0, pool=3.0)


class LLMUnavailableError(Exception):
    """Raised when the configured local model cannot provide a valid answer."""


# @spec[RANCHO_LOCAL_LLM.md#requirements]
class LocalLLMClient:
    """A fixed-path client with internal model policy and redacted failures."""

    def __init__(
        self,
        base_url: str,
        default_model: str,
        complex_model: str | None = None,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._endpoint = _completion_endpoint(base_url)
        self._default_model = default_model
        self._complex_model = complex_model
        self._api_key = api_key
        self._client = client
        self._sleep = sleep

    # @spec[RANCHO_LOCAL_LLM.md#requirements]
    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        high_effort: bool = False,
        temperature: float = 0.0,
        max_output_tokens: int = 512,
    ) -> str:
        """Return a validated assistant message or a typed unavailable error."""
        _validate_request(messages, temperature, max_output_tokens)
        selected_model = self._select_model(high_effort)
        models = [selected_model]
        if selected_model != self._default_model:
            models.append(self._default_model)
        attempts = 0
        for model in models:
            while attempts < _MAX_ATTEMPTS:
                attempts += 1
                try:
                    return self._request(
                        model, messages, temperature, max_output_tokens
                    )
                except _RetryableLLMError:
                    if attempts == _MAX_ATTEMPTS:
                        break
                    if model != self._default_model:
                        break
                    self._sleep(_retry_delay(attempts))
                except LLMUnavailableError:
                    raise
        raise LLMUnavailableError

    def _select_model(self, high_effort: bool) -> str:
        """Apply internal-only model selection policy."""
        if high_effort and self._complex_model:
            return self._complex_model
        return self._default_model

    def _request(
        self,
        model: str,
        messages: Sequence[dict[str, str]],
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    self._endpoint,
                    json=payload,
                    headers=headers,
                    follow_redirects=False,
                    timeout=_TIMEOUT,
                )
            else:
                with httpx.Client(timeout=_TIMEOUT, follow_redirects=False) as client:
                    response = client.post(
                        self._endpoint, json=payload, headers=headers
                    )
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            raise _RetryableLLMError from error
        if response.status_code in _RETRYABLE_STATUS_CODES:
            raise _RetryableLLMError
        if not response.is_success or response.is_redirect:
            raise LLMUnavailableError
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMUnavailableError from error
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailableError
        return content.strip()


class _RetryableLLMError(LLMUnavailableError):
    """An internal error category eligible for a bounded retry."""


# @spec[RANCHO_LOCAL_LLM.md#requirements]
def get_local_llm_client(settings: Settings) -> LocalLLMClient | None:
    """Build the configured trusted local-model client, if enabled."""
    if not settings.llm_is_configured or settings.llm_base_url is None:
        return None
    return LocalLLMClient(
        base_url=str(settings.llm_base_url),
        default_model=settings.llm_model or "",
        complex_model=settings.llm_complex_model,
        api_key=settings.llm_api_key,
    )


def _completion_endpoint(base_url: str) -> str:
    """Fix the provider path so callers cannot use the client as a proxy."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LLMUnavailableError
    return urlunsplit((parsed.scheme, parsed.netloc, "/v1/chat/completions", "", ""))


def _validate_request(
    messages: Sequence[dict[str, str]], temperature: float, max_output_tokens: int
) -> None:
    """Reject oversized or malformed completion requests before any provider call."""
    if not 1 <= len(messages) <= 32 or not 0.0 <= temperature <= 2.0:
        raise LLMUnavailableError
    if not 1 <= max_output_tokens <= 2_048:
        raise LLMUnavailableError
    for message in messages:
        if set(message) != {"role", "content"}:
            raise LLMUnavailableError
        if (
            not message["role"]
            or not message["content"]
            or len(message["content"]) > 12_000
        ):
            raise LLMUnavailableError


def _retry_delay(attempt: int) -> float:
    """Return bounded exponential backoff with jitter."""
    return min(1.0 * (2 ** (attempt - 1)) + random.uniform(0.0, 0.25), 4.0)
