from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.base import AIProvider, ProviderModel, ProviderRequest, ProviderResponse
from app.providers.streaming import ProviderStreamEvent, iter_sse_json, normalize_stream_event


async def _normalized_events(
    provider: str, response: httpx.Response
) -> AsyncIterator[ProviderStreamEvent]:
    async for payload in iter_sse_json(response.aiter_lines()):
        event = normalize_stream_event(provider, payload)
        if event is not None:
            yield event


class OpenAIProvider(AIProvider):
    @staticmethod
    def _payload(request: ProviderRequest, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "instructions": request.system,
            "input": (request.cacheable_prompt_prefix or "") + request.prompt,
            "max_output_tokens": request.max_output_tokens,
            "store": False,
        }
        if stream:
            payload["stream"] = True
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.reasoning_effort != "default":
            payload["reasoning"] = {"effort": request.reasoning_effort}
        if request.response_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "job_result",
                    "strict": False,
                    "schema": request.response_schema,
                }
            }
        return payload

    async def list_models(self) -> list[ProviderModel]:
        response = await self.request(
            "GET",
            "https://api.openai.com/v1/models",
            headers={"authorization": f"Bearer {self.api_key}"},
        )
        data: dict[str, Any] = response.json()
        model_ids = [
            str(item["id"])
            for item in data["data"]
            if str(item["id"]).startswith(("gpt-", "o1", "o3", "o4", "codex"))
        ]
        return sorted(
            [ProviderModel(id=model_id, display_name=model_id) for model_id in model_ids],
            key=lambda item: item.id,
        )

    async def run(self, request: ProviderRequest) -> ProviderResponse:
        response = await self.request(
            "POST",
            "https://api.openai.com/v1/responses",
            timeout_seconds=request.timeout_seconds,
            headers={"authorization": f"Bearer {self.api_key}"},
            json=self._payload(request),
        )
        data: dict[str, Any] = response.json()
        text = "".join(
            part.get("text", "")
            for item in data.get("output", [])
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        )
        usage = data.get("usage") or {}
        return ProviderResponse(
            text=text,
            request_id=data.get("id"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        async with self.client().stream(
            "POST",
            "https://api.openai.com/v1/responses",
            timeout=request.timeout_seconds,
            headers={"authorization": f"Bearer {self.api_key}"},
            json=self._payload(request, stream=True),
        ) as response:
            await self.ensure_stream_success(response)
            async for event in _normalized_events("openai", response):
                yield event


class AnthropicProvider(AIProvider):
    @staticmethod
    def _payload(request: ProviderRequest, *, stream: bool = False) -> dict[str, Any]:
        content: str | list[dict[str, Any]] = request.prompt
        if request.cacheable_prompt_prefix:
            content = [
                {
                    "type": "text",
                    "text": request.cacheable_prompt_prefix,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": request.prompt},
            ]
        payload: dict[str, Any] = {
            "model": request.model,
            "system": [
                {
                    "type": "text",
                    "text": request.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": content}],
            "max_tokens": request.max_output_tokens,
        }
        if stream:
            payload["stream"] = True
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.reasoning_effort != "default":
            payload["thinking"] = {"type": "adaptive"}
            payload["output_config"] = {"effort": request.reasoning_effort}
        return payload

    async def list_models(self) -> list[ProviderModel]:
        response = await self.request(
            "GET",
            "https://api.anthropic.com/v1/models?limit=1000",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        data: dict[str, Any] = response.json()
        return sorted(
            [
                ProviderModel(
                    id=str(item["id"]), display_name=str(item.get("display_name", item["id"]))
                )
                for item in data["data"]
            ],
            key=lambda item: item.id,
        )

    async def run(self, request: ProviderRequest) -> ProviderResponse:
        response = await self.request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            timeout_seconds=request.timeout_seconds,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            json=self._payload(request),
        )
        data: dict[str, Any] = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return ProviderResponse(
            text=text,
            request_id=data.get("id"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        async with self.client().stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            timeout=request.timeout_seconds,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            json=self._payload(request, stream=True),
        ) as response:
            await self.ensure_stream_success(response)
            async for event in _normalized_events("anthropic", response):
                yield event


class GoogleProvider(AIProvider):
    @staticmethod
    def _payload(request: ProviderRequest, *, stream: bool = False) -> dict[str, Any]:
        generation_config: dict[str, Any] = {"max_output_tokens": request.max_output_tokens}
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature
        if request.reasoning_effort != "default":
            generation_config["thinking_level"] = request.reasoning_effort
        payload: dict[str, Any] = {
            "model": request.model,
            "system_instruction": request.system,
            "input": (request.cacheable_prompt_prefix or "") + request.prompt,
            "generation_config": generation_config,
        }
        if stream:
            payload["stream"] = True
        return payload

    async def list_models(self) -> list[ProviderModel]:
        response = await self.request(
            "GET",
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
            headers={"x-goog-api-key": self.api_key},
        )
        data: dict[str, Any] = response.json()
        models = []
        for item in data.get("models", []):
            actions = item.get("supportedGenerationMethods", [])
            if "generateContent" not in actions:
                continue
            model_id = str(item["name"]).removeprefix("models/")
            models.append(
                ProviderModel(id=model_id, display_name=str(item.get("displayName", model_id)))
            )
        return sorted(models, key=lambda item: item.id)

    async def run(self, request: ProviderRequest) -> ProviderResponse:
        response = await self.request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            timeout_seconds=request.timeout_seconds,
            headers={"x-goog-api-key": self.api_key},
            json=self._payload(request),
        )
        data: dict[str, Any] = response.json()
        usage = data.get("usage") or data.get("usageMetadata") or {}
        return ProviderResponse(
            text=data.get("output_text", ""),
            request_id=data.get("id") or data.get("responseId"),
            input_tokens=usage.get("input_tokens") or usage.get("promptTokenCount"),
            output_tokens=usage.get("output_tokens") or usage.get("candidatesTokenCount"),
        )

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        async with self.client().stream(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse",
            timeout=request.timeout_seconds,
            headers={"x-goog-api-key": self.api_key},
            json=self._payload(request, stream=True),
        ) as response:
            await self.ensure_stream_success(response)
            async for event in _normalized_events("google", response):
                yield event
