import asyncio
import hashlib
import hmac
import io
import zipfile
from typing import Any

from app.delivery.domain.provider import MergeReceipt as MergeResult
from app.delivery.domain.provider import PullRequestDetails as PullRequestRead
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

    async def find_open_pull_request(
        self, owner: str, repository: str, head_branch: str
    ) -> PullRequestRead | None:
        response = await integration_http_pool.request(
            "GET",
            f"https://api.github.com/repos/{owner}/{repository}/pulls",
            headers=self.headers,
            params={"state": "open", "head": f"{owner}:{head_branch}", "per_page": 1},
        )
        response.raise_for_status()
        items: list[dict[str, Any]] = response.json()
        if not items:
            return None
        data = items[0]
        return PullRequestRead(
            number=data["number"],
            url=data["html_url"],
            state=data["state"],
            head_sha=data["head"]["sha"],
            merged=bool(data.get("merged", False)),
            merge_commit_sha=data.get("merge_commit_sha"),
        )

    async def create_pull_request(
        self, owner: str, repository: str, head: str, base: str, title: str, body: str
    ) -> PullRequestRead:
        response = await integration_http_pool.request(
            "POST",
            f"https://api.github.com/repos/{owner}/{repository}/pulls",
            retry=False,
            headers=self.headers,
            json={"title": title, "body": body, "head": head, "base": base},
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return PullRequestRead(
            number=data["number"],
            url=data["html_url"],
            state=data["state"],
            head_sha=data["head"]["sha"],
            merged=bool(data.get("merged", False)),
            merge_commit_sha=data.get("merge_commit_sha"),
        )

    async def latest_pull_request_feedback(
        self, owner: str, repository: str, number: int
    ) -> dict[str, str] | None:
        endpoints = (
            f"/repos/{owner}/{repository}/issues/{number}/comments",
            f"/repos/{owner}/{repository}/pulls/{number}/reviews",
            f"/repos/{owner}/{repository}/pulls/{number}/comments",
        )
        feedback: list[dict[str, str]] = []
        for endpoint in endpoints:
            response = await integration_http_pool.request(
                "GET",
                f"https://api.github.com{endpoint}",
                headers=self.headers,
                params={"per_page": 100},
            )
            response.raise_for_status()
            payload: Any = response.json()
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                user = item.get("user") or {}
                author = str(user.get("login") or "") if isinstance(user, dict) else ""
                user_type = str(user.get("type") or "") if isinstance(user, dict) else ""
                body = str(item.get("body") or "").strip()
                if not body or user_type.casefold() == "bot" or author.endswith("[bot]"):
                    continue
                feedback.append(
                    {
                        "author": author,
                        "raw_text": body,
                        "url": str(item.get("html_url") or ""),
                        "created_at": str(item.get("submitted_at") or item.get("created_at") or ""),
                    }
                )
        return max(feedback, key=lambda item: item["created_at"]) if feedback else None

    async def get_pull_request(self, owner: str, repository: str, number: int) -> PullRequestRead:
        response = await integration_http_pool.request(
            "GET",
            f"https://api.github.com/repos/{owner}/{repository}/pulls/{number}",
            headers=self.headers,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return PullRequestRead(
            number=data["number"],
            url=data["html_url"],
            state=data["state"],
            head_sha=data["head"]["sha"],
            merged=bool(data.get("merged", False)),
            merge_commit_sha=data.get("merge_commit_sha"),
        )

    async def update_pull_request(
        self,
        owner: str,
        repository: str,
        number: int,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> None:
        changes = {key: value for key, value in {"title": title, "body": body}.items() if value}
        if not changes:
            return
        response = await integration_http_pool.request(
            "PATCH",
            f"https://api.github.com/repos/{owner}/{repository}/pulls/{number}",
            retry=False,
            headers=self.headers,
            json=changes,
        )
        response.raise_for_status()

    async def collaborator_permission(self, owner: str, repository: str, username: str) -> str:
        response = await integration_http_pool.request(
            "GET",
            f"https://api.github.com/repos/{owner}/{repository}/collaborators/{username}/permission",
            headers=self.headers,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return str(data.get("permission") or "none").casefold()

    async def merge_pull_request(
        self, owner: str, repository: str, number: int, expected_sha: str
    ) -> MergeResult:
        response = await integration_http_pool.request(
            "PUT",
            f"https://api.github.com/repos/{owner}/{repository}/pulls/{number}/merge",
            retry=False,
            headers=self.headers,
            json={"sha": expected_sha, "merge_method": "squash"},
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return MergeResult(
            merged=bool(data.get("merged")), sha=data.get("sha"), message=data.get("message", "")
        )

    async def get_check_run_diagnostics(
        self, owner: str, repository: str, check_run_id: int
    ) -> dict[str, Any]:
        base = f"https://api.github.com/repos/{owner}/{repository}"
        check_response = await integration_http_pool.request(
            "GET", f"{base}/check-runs/{check_run_id}", headers=self.headers
        )
        check_response.raise_for_status()
        check: dict[str, Any] = check_response.json()
        annotations_response = await integration_http_pool.request(
            "GET",
            f"{base}/check-runs/{check_run_id}/annotations",
            headers=self.headers,
            params={"per_page": 100},
        )
        annotations_response.raise_for_status()
        annotations: list[dict[str, Any]] = annotations_response.json()
        actions_log = ""
        external_id = str(check.get("external_id") or "")
        if (check.get("app") or {}).get("slug") == "github-actions" and external_id.isdigit():
            log_response = await integration_http_pool.request(
                "GET",
                f"{base}/actions/jobs/{external_id}/logs",
                headers=self.headers,
            )
            if log_response.status_code < 400:
                actions_log = decode_actions_log(log_response.content)
        return {"check_run": check, "annotations": annotations, "actions_log": actions_log}

    async def list_revision_evidence(
        self, owner: str, repository: str, number: int, revision: str
    ) -> list[dict[str, Any]]:
        """Fetch authoritative current-SHA checks and PR review evidence after downtime."""
        base = f"https://api.github.com/repos/{owner}/{repository}"
        check_runs, statuses, reviews, comments = await asyncio.gather(
            integration_http_pool.request(
                "GET",
                f"{base}/commits/{revision}/check-runs",
                headers=self.headers,
                params={"per_page": 100},
            ),
            integration_http_pool.request(
                "GET",
                f"{base}/commits/{revision}/status",
                headers=self.headers,
                params={"per_page": 100},
            ),
            integration_http_pool.request(
                "GET",
                f"{base}/pulls/{number}/reviews",
                headers=self.headers,
                params={"per_page": 100},
            ),
            integration_http_pool.request(
                "GET",
                f"{base}/pulls/{number}/comments",
                headers=self.headers,
                params={"per_page": 100},
            ),
        )
        for response in (check_runs, statuses, reviews, comments):
            response.raise_for_status()
        evidence: list[dict[str, Any]] = []
        for item in check_runs.json().get("check_runs", []):
            evidence.append(
                {
                    "kind": "CHECK",
                    "name": item.get("name", "check"),
                    "status": str(
                        item.get("conclusion") or item.get("status") or "pending"
                    ).upper(),
                    "revision": item.get("head_sha") or revision,
                    "details_url": item.get("details_url") or item.get("html_url"),
                    "payload": {"check_run": item},
                }
            )
        for item in statuses.json().get("statuses", []):
            evidence.append(
                {
                    "kind": "STATUS",
                    "name": item.get("context", "status"),
                    "status": str(item.get("state", "pending")).upper(),
                    "revision": item.get("sha") or revision,
                    "details_url": item.get("target_url"),
                    "payload": {"status": item},
                }
            )
        for item in reviews.json():
            reviewed_revision = item.get("commit_id")
            if reviewed_revision == revision:
                evidence.append(
                    {
                        "kind": "REVIEW",
                        "name": (item.get("user") or {}).get("login", "review"),
                        "status": str(item.get("state", "commented")).upper(),
                        "revision": reviewed_revision,
                        "details_url": item.get("html_url"),
                        "payload": {"review": item},
                    }
                )
        for item in comments.json():
            commented_revision = item.get("commit_id")
            if commented_revision == revision:
                evidence.append(
                    {
                        "kind": "REVIEW_COMMENT",
                        "name": (item.get("user") or {}).get("login", "review comment"),
                        "status": "ACTION_REQUIRED",
                        "revision": commented_revision,
                        "details_url": item.get("html_url"),
                        "payload": {"review_comment": item},
                    }
                )
        return evidence


def decode_actions_log(content: bytes, max_chars: int = 20_000) -> str:
    """Decode GitHub Actions text/zip logs and retain the failure-heavy tail."""
    chunks: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for name in archive.namelist()[:50]:
                if name.endswith("/"):
                    continue
                chunks.append(archive.read(name).decode(errors="replace"))
    except zipfile.BadZipFile:
        chunks.append(content.decode(errors="replace"))
    text = "\n".join(chunks)
    interesting = [
        line
        for line in text.splitlines()
        if any(
            marker in line.lower()
            for marker in ("error", "failed", "failure", "traceback", "exception", "assert")
        )
    ]
    selected = "\n".join(interesting[-200:]) or text[-max_chars:]
    if len(selected) > max_chars:
        return "[TRUNCATED]\n" + selected[-max_chars:]
    return selected


def verify_signature(body: bytes, secret: str, signature: str | None) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
