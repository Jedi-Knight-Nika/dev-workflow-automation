"""Public CI observations; these facts never grant execution or merge authority."""

import hashlib
import re
from typing import Any
from uuid import UUID

CI_KINDS = frozenset({"check_run", "check_suite", "status"})
CI_STATUSES = frozenset(
    {
        "QUEUED",
        "IN_PROGRESS",
        "PENDING",
        "WAITING",
        "REQUESTED",
        "EXPECTED",
        "SUCCESS",
        "FAILURE",
        "ERROR",
        "TIMED_OUT",
        "CANCELLED",
        "ACTION_REQUIRED",
        "STARTUP_FAILURE",
        "STALE",
        "NEUTRAL",
        "SKIPPED",
        "UNKNOWN",
    }
)


def ci_observation(
    repository_id: UUID, kind: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    if kind not in CI_KINDS:
        return None
    item = payload if kind == "status" else payload.get(kind)
    if not isinstance(item, dict):
        return None
    sha = item.get("sha" if kind == "status" else "head_sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        return None
    status = item.get("state") if kind == "status" else item.get("conclusion") or item.get("status")
    status = status.upper() if isinstance(status, str) else "UNKNOWN"
    # Status deliveries have different IDs for the same context. Check runs/suites
    # have stable execution IDs; a rerun with a new ID is a new observation group.
    identity = item.get("context") if kind == "status" else item.get("id")
    key = None
    if (type(identity) is int and identity > 0) or (
        isinstance(identity, str) and 0 < len(identity) <= 255
    ):
        key = hashlib.sha256(f"{repository_id}:{kind}:{identity}:{sha}".encode()).hexdigest()
    return {
        "repository_id": str(repository_id),
        "head_sha": sha,
        "check_type": kind,
        "check_key": key,
        "status": status if status in CI_STATUSES else "UNKNOWN",
    }
