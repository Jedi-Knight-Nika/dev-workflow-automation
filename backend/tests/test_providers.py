from typing import Any

import httpx
import pytest

from app.db.models import JobRole
from app.infrastructure.workers.structured_output import (
    parse_model_data,
    run_with_structured_repair,
)
from app.providers import AIProvider, ProviderModel, ProviderRequest, ProviderResponse
from app.providers.http import AnthropicProvider, GoogleProvider, OpenAIProvider


class SequenceProvider(AIProvider):
    def __init__(self, responses: list[str]) -> None:
        super().__init__("test")
        self.responses = responses
        self.prompts: list[str] = []

    async def run(self, request: ProviderRequest) -> ProviderResponse:
        self.prompts.append(request.prompt)
        return ProviderResponse(text=self.responses.pop(0), request_id=str(len(self.prompts)))

    async def list_models(self) -> list[ProviderModel]:
        return []


def test_provider_factory_behavior_is_available() -> None:
    provider = OpenAIProvider("secret")
    assert provider.api_key == "secret"


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
