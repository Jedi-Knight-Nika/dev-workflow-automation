import hashlib
import hmac
from typing import Any

from app.platform.integrations.application.ports.integration_discovery import (
    RepositoryDiscoveryView as DiscoveredRepository,
)
from app.platform.integrations.http import integration_http_pool


class GitHubClient:
    def __init__(self, token: str, installation: bool = False) -> None:
        self.installation = installation
        self.headers = {
            "authorization": f"Bearer {token}",
            "accept": "application/vnd.github+json",
            "x-github-api-version": "2022-11-28",
        }

    async def list_repositories(self) -> list[DiscoveredRepository]:
        repositories: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] = {"per_page": 100, "page": page}
            if not self.installation:
                params.update(
                    {
                        "sort": "full_name",
                        "affiliation": "owner,collaborator,organization_member",
                    }
                )
            endpoint = (
                "https://api.github.com/installation/repositories"
                if self.installation
                else "https://api.github.com/user/repos"
            )
            response = await integration_http_pool.request(
                "GET", endpoint, headers=self.headers, params=params
            )
            response.raise_for_status()
            body: Any = response.json()
            batch: list[dict[str, Any]] = body["repositories"] if self.installation else body
            repositories.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return [
            DiscoveredRepository(
                external_repo_id=str(item["id"]),
                owner=item["owner"]["login"],
                name=item["name"],
                full_name=item["full_name"],
                clone_url=item["clone_url"],
                default_branch=item["default_branch"],
                private=item["private"],
            )
            for item in repositories
        ]


def verify_signature(body: bytes, secret: str, signature: str | None) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
