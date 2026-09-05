from typing import Any

import httpx

from app.providers.base import AIProvider, ProviderModel, ProviderRequest, ProviderResponse


class OpenAIProvider(AIProvider):
    async def list_models(self) -> list[ProviderModel]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
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
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"authorization": f"Bearer {self.api_key}"},
                json={
                    "model": request.model,
                    "instructions": request.system,
                    "input": request.prompt,
                    "max_output_tokens": request.max_output_tokens,
                    "store": False,
                },
            )
            response.raise_for_status()
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


class AnthropicProvider(AIProvider):
    async def list_models(self) -> list[ProviderModel]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.anthropic.com/v1/models?limit=1000",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            )
            response.raise_for_status()
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
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": request.model,
                    "system": request.system,
                    "messages": [{"role": "user", "content": request.prompt}],
                    "max_tokens": request.max_output_tokens,
                },
            )
            response.raise_for_status()
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


class GoogleProvider(AIProvider):
    async def list_models(self) -> list[ProviderModel]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                headers={"x-goog-api-key": self.api_key},
            )
            response.raise_for_status()
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
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": self.api_key},
                json={
                    "model": request.model,
                    "system_instruction": request.system,
                    "input": request.prompt,
                },
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        usage = data.get("usage") or data.get("usageMetadata") or {}
        return ProviderResponse(
            text=data.get("output_text", ""),
            request_id=data.get("id") or data.get("responseId"),
            input_tokens=usage.get("input_tokens") or usage.get("promptTokenCount"),
            output_tokens=usage.get("output_tokens") or usage.get("candidatesTokenCount"),
        )
