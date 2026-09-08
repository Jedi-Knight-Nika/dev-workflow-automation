"""Authoritative, paginated GitHub evidence. Webhooks only trigger rechecks."""

import re
from typing import Any

import httpx

from app.delivery.domain.merge import Approval, MergeEvidence, MergePolicy


class GitHubDelivery:
    def __init__(self, client: httpx.AsyncClient, owner: str, repository: str) -> None:
        self.client = client
        self.root = f"/repos/{owner}/{repository}"

    async def get(self, path: str) -> Any:
        response = await self.client.get(self.root + path)
        response.raise_for_status()
        return response.json()

    async def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for page in range(1, 21):
            separator = "&" if "?" in path else "?"
            result = await self.get(f"{path}{separator}per_page=100&page={page}")
            items = result[key] if key else result
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ValueError("Invalid GitHub evidence")
            values.extend(items)
            if len(items) < 100:
                return values
        raise ValueError("GitHub evidence exceeds pagination bound; cannot safely merge")

    async def publish(
        self, *, branch: str, base: str, title: str, body: str, owner: str, expected_sha: str
    ) -> dict[str, Any]:
        response = await self.client.get(
            self.root + "/pulls",
            params={"state": "open", "head": f"{owner}:{branch}", "base": base, "per_page": 100},
        )
        response.raise_for_status()
        found = response.json()
        if len(found) > 1:
            raise ValueError("Ambiguous PR for task branch")
        if found:
            pull = await self.get(f"/pulls/{found[0]['number']}")
        else:
            response = await self.client.post(
                self.root + "/pulls",
                json={
                    "head": branch,
                    "base": base,
                    "title": title[:250],
                    "body": body[:16000],
                    "maintainer_can_modify": False,
                },
            )
            response.raise_for_status()
            pull = response.json()
        if pull["head"]["sha"] != expected_sha:
            raise ValueError("PR head differs from the validated/pushed revision")
        return dict(pull)

    async def evidence(
        self,
        number: int,
        expected_sha: str,
        validated_sha: str | None,
        policy: MergePolicy,
        required_checks: tuple[str, ...],
        *,
        runnable: bool,
    ) -> tuple[MergeEvidence, dict[str, Any]]:
        pull = await self.get(f"/pulls/{number}")
        sha = pull["head"]["sha"]
        reviews = await self.pages(f"/pulls/{number}/reviews")
        latest: dict[str, dict[str, Any]] = {}
        for review in sorted(reviews, key=lambda value: value["id"]):
            if review.get("state") in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                latest[str(review["user"]["id"])] = review
        approvals = [
            value
            for actor, value in latest.items()
            if actor in policy.authorized_actor_ids
            and value.get("state") == "APPROVED"
            and value.get("commit_id") == sha
            and value.get("user", {}).get("type") == "User"
            and actor != str(pull["user"]["id"])
        ]
        approval = None
        if approvals:
            chosen = max(approvals, key=lambda value: value["id"])
            approval = Approval(str(chosen["user"]["id"]), sha, str(chosen["id"]))
        elif not policy.require_formal_approval:
            comments = await self.pages(f"/issues/{number}/comments")
            commands = [
                value
                for value in comments
                if (
                    str(value.get("user", {}).get("id")) in policy.authorized_actor_ids
                    and str(value.get("user", {}).get("id")) != str(pull["user"]["id"])
                    and value.get("user", {}).get("type") == "User"
                    and latest.get(str(value.get("user", {}).get("id")), {}).get("state")
                    not in {"CHANGES_REQUESTED", "DISMISSED"}
                    and re.fullmatch(
                        r"/lgtm " + re.escape(sha), str(value.get("body") or "").strip()
                    )
                )
            ]
            if commands:
                chosen = max(commands, key=lambda value: value["id"])
                approval = Approval(
                    str(chosen["user"]["id"]), sha, f"comment:{chosen['id']}", formal=False
                )
        checks = await self.pages(f"/commits/{sha}/check-runs?filter=latest", "check_runs")
        statuses = await self.pages(f"/commits/{sha}/statuses")
        states: dict[tuple[str, str], bool] = {}
        for check in checks:
            key = ("check", check["name"])
            ok = (
                check.get("head_sha") == sha
                and check.get("status") == "completed"
                and check.get("conclusion") == "success"
            )
            states[key] = states.get(key, True) and ok
        for status in sorted(statuses, key=lambda value: value["id"], reverse=True):
            states.setdefault(("status", status["context"]), status.get("state") == "success")
        complete = bool(required_checks) and all(
            any(key[1] == name for key in states) for name in required_checks
        )
        green = complete and all(ok for key, ok in states.items() if key[1] in required_checks)
        evidence = MergeEvidence(
            expected_sha=expected_sha,
            current_sha=sha,
            validated_sha=validated_sha,
            pr_open=pull.get("state") == "open" and not pull.get("draft", False),
            checks_complete=complete,
            checks_passed=green,
            blocking_review=any(value["state"] == "CHANGES_REQUESTED" for value in latest.values()),
            mergeable=pull.get("mergeable") is True and pull.get("mergeable_state") == "clean",
            task_runnable=runnable,
            approval=approval,
        )
        return evidence, pull

    async def merge(self, number: int, sha: str) -> dict[str, Any]:
        response = await self.client.put(
            self.root + f"/pulls/{number}/merge", json={"sha": sha, "merge_method": "squash"}
        )
        response.raise_for_status()
        result = response.json()
        if result.get("merged") is not True:
            raise ValueError("GitHub did not confirm the merge")
        return dict(result)


def github_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
        follow_redirects=False,
    )
