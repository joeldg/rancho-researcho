"""Controlled contract tests for the local OpenAI-compatible LLM client."""

import json

import httpx
import pytest

from rancho.llm import LLMUnavailableError, LocalLLMClient


# @spec[RANCHO_LOCAL_LLM.md#acceptance-evidence]
def test_client_uses_fixed_path_and_returns_assistant_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://ollama.internal/v1/chat/completions"
        assert json.loads(request.content)["model"] == "llama3.1:8b"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Grounded answer."}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = LocalLLMClient(
        "http://ollama.internal/ignored", "llama3.1:8b", client=client
    )
    try:
        answer = llm.complete([{"role": "user", "content": "Summarize evidence."}])
    finally:
        client.close()

    assert answer == "Grounded answer."


# @spec[RANCHO_LOCAL_LLM.md#acceptance-evidence]
def test_retryable_complex_model_failure_falls_back_to_default() -> None:
    requested_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        requested_models.append(model)
        if model == "large-model":
            return httpx.Response(503, text="SENSITIVE OOM DETAIL")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Fallback answer."}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = LocalLLMClient(
        "http://vllm.internal",
        "small-model",
        complex_model="large-model",
        client=client,
        sleep=lambda _: None,
    )
    try:
        answer = llm.complete(
            [{"role": "user", "content": "Analyze."}], high_effort=True
        )
    finally:
        client.close()

    assert answer == "Fallback answer."
    assert requested_models == ["large-model", "small-model"]


# @spec[RANCHO_LOCAL_LLM.md#acceptance-evidence]
def test_malformed_response_is_unavailable_without_provider_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "SENSITIVE PROVIDER BODY"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = LocalLLMClient("http://ollama.internal", "model", client=client)
    try:
        with pytest.raises(LLMUnavailableError) as error:
            llm.complete([{"role": "user", "content": "Hello"}])
    finally:
        client.close()

    assert "SENSITIVE" not in str(error.value)
