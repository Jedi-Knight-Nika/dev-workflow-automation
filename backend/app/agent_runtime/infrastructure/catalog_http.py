from typing import Any

from app.agent_runtime.infrastructure.catalog_base import AIProvider, ProviderModel


class OpenAIProvider(AIProvider):
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


class AnthropicProvider(AIProvider):
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


class DeepSeekProvider(AIProvider):
    """Discovery uses the provider's documented GET /models endpoint."""

    async def list_models(self) -> list[ProviderModel]:
        response = await self.request(
            "GET",
            "https://api.deepseek.com/models",
            headers={"authorization": f"Bearer {self.api_key}"},
        )
        return sorted(
            [
                ProviderModel(id=str(item["id"]), display_name=str(item["id"]))
                for item in response.json()["data"]
            ],
            key=lambda item: item.id,
        )
