"""Bounded, public activity metadata. Raw source payloads never reach a renderer."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from app.agent_runtime.domain.work_history import public_work_plans
from app.coordinator.domain.protocol import Directive
from app.engineering.domain.lifecycle import Action, Stage, TaskStatus, WaitReason
from app.intake.domain.ci import CI_KINDS, CI_STATUSES

_ENUM_FACTS: dict[str, frozenset[str]] = {
    "from_status": frozenset(TaskStatus),
    "to_status": frozenset(TaskStatus),
    "from_stage": frozenset(Stage),
    "to_stage": frozenset(Stage),
    "wait_reason": frozenset(WaitReason),
    "action": frozenset(Action) | frozenset(Directive),
}

_EVENT_KINDS = {
    "TASK_LIFECYCLE_CHANGED": "TASK_STATE_CHANGED",
    "ENGINEERING_MERGE_CONFIRMED": "MERGE_COMPLETED",
    "HUMAN_INPUT_REQUIRED": "HUMAN_REQUIRED",
    "HUMAN_INPUT_RESOLVED": "HUMAN_RESPONDED",
}


@dataclass(frozen=True)
class Activity:
    source_type: str
    source_id: str
    task_id: UUID
    kind: str
    occurred_at: datetime
    actor_type: str = "system"
    actor: str = "Engineering"
    detail_level: int = 1
    correlation_id: UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    references: list[dict[str, str]] = field(default_factory=list)


def reference(source: str, identity: object, relationship: str) -> dict[str, str]:
    return {"source_type": source, "source_id": str(identity), "relationship": relationship}


def identifier(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


def amount(value: object) -> str | None:
    try:
        number = Decimal(str(value))
        return str(number) if number.is_finite() and number >= 0 else None
    except InvalidOperation:
        return None


def file_path(value: str) -> str | None:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 1000
        or path.is_absolute()
        or ".." in path.parts
        or any(ord(char) < 32 or char in "|\\" for char in value)
    ):
        return None
    return str(path)


def task_activity(
    event_id: int, task_id: UUID, kind: str, payload: dict[str, Any], at: datetime, source: str
) -> Activity:
    # Only enumerated facts and identifiers are copied. No prompts, feedback,
    # arbitrary errors, URLs, message bodies, or provider context are exposed.
    public: dict[str, Any] = {}
    for key, values in _ENUM_FACTS.items():
        value = payload.get(key)
        if isinstance(value, str) and value in values:
            public[key] = value
    for key in ("version", "requirement_version", "priority"):
        value = payload.get(key)
        if type(value) is int and value >= 0:
            public[key] = value
    for key in ("run_id", "job_id", "request_id", "action_id", "review_cycle_id", "repository_id"):
        value_id = identifier(payload.get(key))
        if value_id:
            public[key] = str(value_id)
    for key in ("passed", "from_manual_takeover", "manual_takeover"):
        if type(payload.get(key)) is bool:
            public[key] = payload[key]
    if kind == "CI_CHECK_UPDATED":
        for key, allowed in (("status", CI_STATUSES), ("check_type", CI_KINDS)):
            if isinstance(payload.get(key), str) and payload[key] in allowed:
                public[key] = payload[key]
        check_key = payload.get("check_key")
        if isinstance(check_key, str) and re.fullmatch(r"[0-9a-f]{64}", check_key):
            public["check_key"] = check_key
    for key in ("parent_event_id", "omitted_causes"):
        if type(payload.get(key)) is int and 0 < payload[key] <= 2**53 - 1:
            public[key] = payload[key]
    if isinstance(payload.get("review_cycle_ids"), list):
        public["review_cycle_ids"] = [
            str(id) for value in payload["review_cycle_ids"][:50] if (id := identifier(value))
        ]
    for key in ("head_sha", "merge_sha"):
        value = payload.get(key)
        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40,64}", value):
            public[key] = value
    if kind == "ENGINEERING_COST_RECONCILED":
        public["cost_usd"] = amount(payload.get("amount_usd"))
    if kind == "WORK_PLAN_UPDATED":
        public["work_plans"] = public_work_plans(payload.get("work_plans"))
    if kind == "TASK_DEPENDENCIES_CHANGED" and isinstance(payload.get("dependency_ids"), list):
        public["dependency_ids"] = [
            str(id) for value in payload["dependency_ids"][:32] if (id := identifier(value))
        ]
    if kind == "VALIDATION_BATCH_COMPLETED":
        kind = "VALIDATION_PASSED" if payload.get("passed") is True else "VALIDATION_FAILED"
    else:
        kind = _EVENT_KINDS.get(kind, kind)
    actor_type, actor = activity_actor(kind, source, payload.get("actor"))
    return Activity(
        "task_event",
        str(event_id),
        task_id,
        kind[:100],
        at,
        actor_type,
        actor,
        1
        if kind
        in {
            "TASK_CREATED",
            "TASK_STATE_CHANGED",
            "HUMAN_REQUIRED",
            "HUMAN_RESPONDED",
            "MERGE_COMPLETED",
        }
        else 2,
        identifier(payload.get("run_id") or payload.get("job_id")),
        public,
    )


def activity_actor(kind: str, source: str, lifecycle_actor: object) -> tuple[str, str]:
    if kind == "WORK_PLAN_UPDATED":
        return "agent", "Developer"
    if kind != "TASK_STATE_CHANGED":
        lifecycle_actor = None
    if kind.startswith("COORDINATOR_") or lifecycle_actor == "coordinator":
        return "agent", "Coordinator"
    if source in {"github", "trello", "linear", "slack"}:
        return "integration", source.title()
    if source in {"user", "dashboard", "api"} or (
        isinstance(lifecycle_actor, str) and lifecycle_actor.startswith("user:")
    ):
        return "human", "Human"
    return "system", "Engineering"


def check_kind(command: object) -> str:
    """Classify known check names without exposing command arguments or private paths."""
    tokens = {str(part).lower() for part in command[:10]} if isinstance(command, list) else set()
    for name, known in (
        ("typecheck", {"mypy", "tsc", "typecheck", "svelte-check"}),
        ("lint", {"ruff", "eslint", "lint"}),
        ("tests", {"pytest", "test", "vitest", "playwright"}),
        ("build", {"build", "compile"}),
    ):
        if tokens & known:
            return name
    return "check"
