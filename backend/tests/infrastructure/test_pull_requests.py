from typing import Any

import httpx
import pytest

from app.delivery.infrastructure.github_client import GitHubClient


@pytest.mark.asyncio
async def test_repository_discovery_follows_github_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        count = 100 if page == 1 else 1
        return httpx.Response(
            200,
            json=[
                {
                    "id": page * 1000 + index,
                    "owner": {"login": "acme"},
                    "name": f"service-{page}-{index}",
                    "full_name": f"acme/service-{page}-{index}",
                    "clone_url": "https://github.com/acme/service.git",
                    "default_branch": "main",
                    "private": True,
                }
                for index in range(count)
            ],
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    repositories = await GitHubClient("secret").list_repositories()

    assert len(repositories) == 101
    assert [request.url.params["page"] for request in requests] == ["1", "2"]
