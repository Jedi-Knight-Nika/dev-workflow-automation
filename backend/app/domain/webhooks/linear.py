import uuid
from typing import Any


def linear_priority(value: object) -> int:
    if not isinstance(value, int):
        return 3
    return {1: 1, 2: 3, 3: 3, 4: 4}.get(value, 3)


def issue_labels(data: dict[str, Any]) -> set[str]:
    labels = data.get("labels") or []
    if isinstance(labels, dict):
        labels = labels.get("nodes") or []
    return {str(item.get("name")) for item in labels if isinstance(item, dict) and item.get("name")}


def configured_repository_id(configuration: dict[str, Any]) -> uuid.UUID | None:
    value = configuration.get("repository_id")
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def linear_comment(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if payload.get("type") != "Comment" or payload.get("action") not in {
        "create",
        "update",
    }:
        return None
    data = payload.get("data") or {}
    issue = data.get("issue") or {}
    identifier = issue.get("identifier") or data.get("issueIdentifier")
    body = str(data.get("body") or "").strip()
    if not identifier or not body:
        return None
    return str(identifier), {
        "source": "linear",
        "event_type": "comment",
        "author": (data.get("user") or {}).get("name"),
        "url": data.get("url"),
        "raw_text": body,
    }
