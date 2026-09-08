import httpx
import pytest

from app.agent_runtime.infrastructure.catalog_factory import create_provider


@pytest.mark.asyncio
async def test_deepseek_discovery_uses_authenticated_catalog_not_inference() -> None:
    provider = create_provider("deepseek", "unit-key")
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://api.deepseek.com/models"
        assert request.headers["authorization"] == "Bearer unit-key"
        return httpx.Response(200, json={"data": [{"id": "unit-model"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider._client = client
        models = await provider.list_models()
    assert [model.id for model in models] == ["unit-model"]
    assert len(calls) == 1
