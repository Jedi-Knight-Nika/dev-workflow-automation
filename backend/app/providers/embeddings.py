from typing import Any

import httpx


class OpenAIEmbeddings:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self.model = model
        self.headers = {"authorization": f"Bearer {api_key}", "content-type": "application/json"}

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=120, headers=self.headers) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                json={"model": self.model, "input": inputs, "dimensions": 1536},
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        ordered = sorted(body.get("data", []), key=lambda item: item["index"])
        return [item["embedding"] for item in ordered]
