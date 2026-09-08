from datetime import datetime
from typing import Any

from app.delivery.domain.review import ReviewMessage


def human_message(
    source: str, value: dict[str, Any], sha: str, validated_at: datetime | None
) -> ReviewMessage | None:
    """Bind provider-fetched text to a validated revision, never a SHA in prose."""
    user = value.get("user") or {}
    if user.get("type") != "User" or not user.get("id") or validated_at is None:
        return None
    body = str(value.get("body") or "").strip()
    if not body or value.get("commit_id", sha) != sha:
        return None
    timestamp = str(value.get("updated_at") or value.get("submitted_at") or "")
    try:
        observed = datetime.fromisoformat(timestamp)
        if observed.tzinfo is None or observed < validated_at:
            return None
    except (TypeError, ValueError):
        return None
    return ReviewMessage(source, str(value["id"]), str(user["id"]), sha, body, timestamp)
