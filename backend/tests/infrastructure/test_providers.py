import json
from typing import Any

import httpx
import pytest

from app.db.models import JobRole
from app.infrastructure.workers.structured_output import (
    ProviderAttempt,
    parse_model_data,
    run_with_structured_repair,
)
from app.providers import (
    AIProvider,
    ProviderModel,
    ProviderRequest,
    ProviderRequestError,
    ProviderResponse,
)
from app.providers.http import AnthropicProvider, GoogleProvider, OpenAIProvider


class SequenceProvider(AIProvider):
    def __init__(self, responses: list[str]) -> None:
        super().__init__("test")
        self.responses = responses
        self.prompts: list[str] = []
        self.cacheable_prefixes: list[str | None] = []

    async def run(self, request: ProviderRequest) -> ProviderResponse:
        self.prompts.append(request.prompt)
        self.cacheable_prefixes.append(request.cacheable_prompt_prefix)
        return ProviderResponse(text=self.responses.pop(0), request_id=str(len(self.prompts)))

    async def list_models(self) -> list[ProviderModel]:
        return []


def test_provider_factory_behavior_is_available() -> None:
    provider = OpenAIProvider("secret")
    assert provider.api_key == "secret"


@pytest.mark.parametrize(
    "provider_type",
    [OpenAIProvider, AnthropicProvider, GoogleProvider],
)
def test_streaming_and_non_streaming_use_the_same_runtime_mapping(
    provider_type: type[OpenAIProvider | AnthropicProvider | GoogleProvider],
) -> None:
    request = ProviderRequest(
        model="test-model",
        system="system",
        prompt="prompt",
        max_output_tokens=8_000,
        temperature=0.2,
        reasoning_effort="high",
        cacheable_prompt_prefix="cached-prefix",
    )

    standard = provider_type._payload(request)
    streaming = provider_type._payload(request, stream=True)

    assert streaming == {**standard, "stream": True}


def test_normalized_runtime_fields_map_to_provider_specific_parameters() -> None:
    request = ProviderRequest(
        model="test-model",
        system="system",
        prompt="prompt",
        max_output_tokens=8_000,
        reasoning_effort="high",
    )

    openai = OpenAIProvider._payload(request)
    anthropic = AnthropicProvider._payload(request)
    google = GoogleProvider._payload(request)

    assert openai["max_output_tokens"] == 8_000
    assert openai["reasoning"] == {"effort": "high"}
    assert anthropic["max_tokens"] == 8_000
    assert anthropic["thinking"] == {"type": "adaptive"}
    assert anthropic["output_config"] == {"effort": "high"}
    assert google["generation_config"] == {
        "max_output_tokens": 8_000,
        "thinking_level": "high",
    }


def test_openai_receives_structured_job_result_schema() -> None:
    schema = {"type": "object", "properties": {"result": {"type": "string"}}}

    payload = OpenAIProvider._payload(
        ProviderRequest(
            model="test-model",
            system="system",
            prompt="prompt",
            response_schema=schema,
        )
    )

    assert payload["text"]["format"] == {
        "type": "json_schema",
        "name": "job_result",
        "strict": False,
        "schema": schema,
    }


def test_model_json_is_parsed() -> None:
    assert parse_model_data('```json\n{"result": "PASS"}\n```') == {"result": "PASS"}


def test_non_json_model_output_is_preserved() -> None:
    assert parse_model_data("plain text") == {"text": "plain text"}


@pytest.mark.asyncio
async def test_provider_model_catalogs_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openai.com":
            assert request.headers["authorization"] == "Bearer secret"
            return httpx.Response(200, json={"data": [{"id": "whisper-1"}, {"id": "gpt-5"}]})
        if request.url.host == "api.anthropic.com":
            assert request.headers["x-api-key"] == "secret"
            return httpx.Response(
                200, json={"data": [{"id": "claude-sonnet", "display_name": "Claude Sonnet"}]}
            )
        assert request.headers["x-goog-api-key"] == "secret"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-pro",
                        "displayName": "Gemini Pro",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/embedding",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    openai = await OpenAIProvider("secret").list_models()
    anthropic = await AnthropicProvider("secret").list_models()
    google = await GoogleProvider("secret").list_models()

    assert [(model.id, model.display_name) for model in openai] == [("gpt-5", "gpt-5")]
    assert anthropic[0].display_name == "Claude Sonnet"
    assert [(model.id, model.display_name) for model in google] == [("gemini-pro", "Gemini Pro")]


@pytest.mark.asyncio
async def test_transient_provider_failures_are_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "temporarily unavailable"})
        return httpx.Response(200, json={"data": []})

    async def no_sleep(_delay: float) -> None:
        return None

    transport = httpx.MockTransport(handler)
    provider = OpenAIProvider("secret")
    provider._client = httpx.AsyncClient(transport=transport)
    monkeypatch.setattr("app.providers.base.asyncio.sleep", no_sleep)
    try:
        assert await provider.list_models() == []
    finally:
        await provider.aclose()
    assert attempts == 3


@pytest.mark.asyncio
async def test_missing_model_is_normalized_without_leaking_provider_body() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"error": {"message": "Model private-model-name was not found"}},
        )

    provider = OpenAIProvider("secret")
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ProviderRequestError) as raised:
            await provider.run(ProviderRequest(model="missing", system="system", prompt="prompt"))
    finally:
        await provider.aclose()

    assert raised.value.code == "MODEL_UNAVAILABLE"
    assert raised.value.status_code == 404
    assert "private-model-name" not in str(raised.value)


@pytest.mark.asyncio
async def test_streaming_configuration_error_is_normalized() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Unsupported parameter"}})

    provider = AnthropicProvider("secret")
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ProviderRequestError) as raised:
            async for _event in provider.stream(
                ProviderRequest(model="claude-test", system="system", prompt="prompt")
            ):
                pass
    finally:
        await provider.aclose()

    assert raised.value.code == "MODEL_POLICY_ERROR"


@pytest.mark.asyncio
async def test_anthropic_marks_static_prompt_sections_cacheable() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"id": "msg-1", "content": [{"type": "text", "text": "ok"}]},
        )

    provider = AnthropicProvider("secret")
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        await provider.run(
            ProviderRequest(
                model="claude-test",
                system="static system",
                prompt="repair suffix",
                cacheable_prompt_prefix="large original context",
            )
        )
    finally:
        await provider.aclose()

    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert captured["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "body", "expected_id"),
    [
        (
            OpenAIProvider("secret"),
            (
                'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
                'data: {"type":"response.completed","response":{"id":"resp-1",'
                '"usage":{"input_tokens":3,"output_tokens":1}}}\n\n'
            ),
            "resp-1",
        ),
        (
            AnthropicProvider("secret"),
            (
                'data: {"type":"message_start","message":{"id":"msg-1",'
                '"usage":{"input_tokens":3}}}\n\n'
                'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
                '"text":"hello"}}\n\n'
                'data: {"type":"message_delta","usage":{"output_tokens":1}}\n\n'
            ),
            "msg-1",
        ),
        (
            GoogleProvider("secret"),
            (
                'data: {"event_type":"step.delta","delta":{"type":"text",'
                '"text":"hello"}}\n\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"int-1",'
                '"usage":{"total_input_tokens":3,"total_output_tokens":1}}}\n\n'
            ),
            "int-1",
        ),
    ],
)
async def test_provider_adapters_expose_normalized_streams(
    provider: AIProvider, body: str, expected_id: str
) -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        events = [
            event
            async for event in provider.stream(
                ProviderRequest(model="test-model", system="system", prompt="prompt")
            )
        ]
    finally:
        await provider.aclose()

    assert "".join(event.text_delta for event in events) == "hello"
    assert next(event.request_id for event in events if event.request_id) == expected_id
    assert any(event.completed for event in events)
    assert captured["stream"] is True


@pytest.mark.asyncio
async def test_invalid_structured_output_is_repaired_once() -> None:
    provider = SequenceProvider(
        [
            "not json",
            '{"result":"PASS","summary":"Clean","findings":[]}',
        ]
    )
    data, attempts = await run_with_structured_repair(
        provider,
        ProviderRequest(model="test", system="review", prompt="original context"),
        JobRole.REVIEWER,
    )

    assert data["result"] == "PASS"
    assert len(attempts) == 2
    assert provider.prompts[0] == "original context"
    assert "failed schema validation" in provider.prompts[1]
    assert provider.cacheable_prefixes == [None, "original context"]


@pytest.mark.asyncio
async def test_structured_output_repairs_are_bounded() -> None:
    provider = SequenceProvider(["bad", "still bad", "bad again"])
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        await run_with_structured_repair(
            provider,
            ProviderRequest(model="test", system="review", prompt="context"),
            JobRole.REVIEWER,
        )
    assert len(provider.prompts) == 3


@pytest.mark.asyncio
async def test_budget_hook_runs_before_every_provider_attempt() -> None:
    provider = SequenceProvider(
        [
            "bad",
            '{"result":"PASS","summary":"Clean","findings":[]}',
        ]
    )
    observed_attempt_counts: list[int] = []

    async def check_budget(attempts: list[ProviderAttempt]) -> None:
        observed_attempt_counts.append(len(attempts))

    await run_with_structured_repair(
        provider,
        ProviderRequest(model="test", system="review", prompt="context"),
        JobRole.REVIEWER,
        before_attempt=check_budget,
    )

    assert observed_attempt_counts == [0, 1]


from app.worker import estimate_cost_usd


def test_estimated_cost_uses_explicit_per_million_rates() -> None:
    assert (
        estimate_cost_usd(
            1_000_000,
            500_000,
            {
                "input_cost_per_million": 2,
                "output_cost_per_million": 8,
            },
        )
        == 6
    )
    assert estimate_cost_usd(100, 100, {}) is None
