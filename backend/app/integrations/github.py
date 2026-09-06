import asyncio
import hashlib
import hmac
import io
import zipfile
from typing import Any

import httpx

from app.schemas import DiscoveredRepository, MergeResult, PullRequestRead


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
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
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
                response = await client.get(endpoint, params=params)
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
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repository}/pulls",
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
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.post(
                f"https://api.github.com/repos/{owner}/{repository}/pulls",
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

    async def get_pull_request(self, owner: str, repository: str, number: int) -> PullRequestRead:
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repository}/pulls/{number}"
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

    async def merge_pull_request(
        self, owner: str, repository: str, number: int, expected_sha: str
    ) -> MergeResult:
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            response = await client.put(
                f"https://api.github.com/repos/{owner}/{repository}/pulls/{number}/merge",
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
        async with httpx.AsyncClient(
            timeout=30, headers=self.headers, follow_redirects=True
        ) as client:
            check_response = await client.get(
                f"https://api.github.com/repos/{owner}/{repository}/check-runs/{check_run_id}"
            )
            check_response.raise_for_status()
            check: dict[str, Any] = check_response.json()
            annotations_response = await client.get(
                f"https://api.github.com/repos/{owner}/{repository}/check-runs/{check_run_id}/annotations",
                params={"per_page": 100},
            )
            annotations_response.raise_for_status()
            annotations: list[dict[str, Any]] = annotations_response.json()
            actions_log = ""
            external_id = str(check.get("external_id") or "")
            if (check.get("app") or {}).get("slug") == "github-actions" and external_id.isdigit():
                log_response = await client.get(
                    f"https://api.github.com/repos/{owner}/{repository}/actions/jobs/{external_id}/logs"
                )
                if log_response.status_code < 400:
                    actions_log = decode_actions_log(log_response.content)
        return {"check_run": check, "annotations": annotations, "actions_log": actions_log}

    async def list_revision_evidence(
        self, owner: str, repository: str, number: int, revision: str
    ) -> list[dict[str, Any]]:
        """Fetch authoritative current-SHA checks and PR review evidence after downtime."""
        base = f"https://api.github.com/repos/{owner}/{repository}"
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            check_runs, statuses, reviews, comments = await asyncio.gather(
                client.get(f"{base}/commits/{revision}/check-runs", params={"per_page": 100}),
                client.get(f"{base}/commits/{revision}/status", params={"per_page": 100}),
                client.get(f"{base}/pulls/{number}/reviews", params={"per_page": 100}),
                client.get(f"{base}/pulls/{number}/comments", params={"per_page": 100}),
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
