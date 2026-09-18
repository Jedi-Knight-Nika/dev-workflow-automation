"""Bounded GitHub evidence and reviewer requests scoped by current task policy."""

from collections.abc import Awaitable, Callable
from typing import Any

Request = Callable[..., Awaitable[Any]]


async def read_github(
    request: Request,
    root: str,
    headers: dict[str, str],
    target: dict[str, Any],
    tool: str,
) -> dict[str, Any]:
    pull = await request("GET", f"{root}/pulls/{target['number']}", headers)
    sha = pull["head"]["sha"]
    result: dict[str, Any] = {"head_sha": sha, "bounded_excerpt": True}
    if tool == "READ_CHECKS":
        checks = await request(
            "GET", f"{root}/commits/{sha}/check-runs", headers, params={"per_page": 100}
        )
        statuses = await request(
            "GET", f"{root}/commits/{sha}/status", headers, params={"per_page": 100}
        )
        result.update(
            checks=[
                {k: row.get(k) for k in ("name", "status", "conclusion")}
                for row in checks.get("check_runs", [])
            ],
            statuses=[
                {k: row.get(k) for k in ("context", "state", "description")}
                for row in statuses.get("statuses", [])
            ],
            checks_truncated=checks.get("total_count", 0) > 100,
            status=statuses.get("state"),
        )
    elif tool == "READ_REVIEW_DELTA":
        comments = await request(
            "GET",
            f"{root}/pulls/{target['number']}/comments",
            headers,
            params={"per_page": 20, "sort": "updated", "direction": "desc"},
        )
        result["comments"] = [
            {
                "id": row["id"],
                "path": row.get("path"),
                "line": row.get("line"),
                "commit_id": row.get("commit_id"),
                "body": str(row.get("body") or "")[:1000],
            }
            for row in comments
        ]
    else:
        # Explicitly mark a full page incomplete; it cannot prove absence of newer reviews.
        reviews = await request(
            "GET", f"{root}/pulls/{target['number']}/reviews", headers, params={"per_page": 100}
        )
        result["reviews"] = [
            {
                "id": row["id"],
                "actor": str(row["user"]["id"]),
                "state": row["state"],
                "commit_id": row.get("commit_id"),
                "body": str(row.get("body") or "")[:600],
            }
            for row in reviews[-20:]
        ]
        result["history_incomplete"] = len(reviews) >= 100
    return result


async def request_review(
    request: Request,
    root: str,
    headers: dict[str, str],
    target: dict[str, Any],
    reviewers: tuple[str, ...],
) -> str:
    if not reviewers or len(reviewers) > 10:
        raise ValueError("Configure between one and ten explicit reviewer IDs")
    pull = await request("GET", f"{root}/pulls/{target['number']}", headers)
    if pull["head"]["sha"] != target["sha"] or pull.get("state") != "open" or pull.get("draft"):
        raise ValueError("Review request requires the current open, ready PR revision")
    requested = {str(user["id"]) for user in pull.get("requested_reviewers", [])}
    author = str(pull["user"]["id"])
    allowed = set(reviewers) - {author}
    if not allowed:
        raise ValueError("Configured reviewers contain only the PR author")
    logins = []
    for actor in sorted(allowed - requested):
        if not actor.isdecimal():
            raise ValueError("Reviewer IDs must be immutable numeric identities")
        user = await request("GET", f"https://api.github.com/user/{actor}", headers)
        if str(user["id"]) != actor or user.get("type") != "User":
            raise ValueError("Reviewer identity is not an authorized human")
        logins.append(user["login"])
    if logins:
        # Refresh after identity lookup; no automatic retry if the POST is uncertain.
        current = await request("GET", f"{root}/pulls/{target['number']}", headers)
        if (
            current["head"]["sha"] != target["sha"]
            or current.get("state") != "open"
            or current.get("draft")
        ):
            raise ValueError("PR changed before requesting reviewers")
        result = await request(
            "POST",
            f"{root}/pulls/{target['number']}/requested_reviewers",
            headers,
            json={"reviewers": logins},
        )
        if not allowed <= {str(user["id"]) for user in result.get("requested_reviewers", [])}:
            raise ValueError("GitHub did not confirm every requested reviewer")
    return f"review:{target['number']}:{target['sha']}"
