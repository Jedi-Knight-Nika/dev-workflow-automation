"""Immutable deployment observations; no deployment or merge authority."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

DEPLOYMENT_STATUSES = frozenset(
    {"CREATED", "QUEUED", "PENDING", "IN_PROGRESS", "SUCCESS", "FAILURE", "ERROR", "INACTIVE"}
)


@dataclass(frozen=True, slots=True)
class DeploymentFact:
    deployment_id: str
    observation_id: str
    sha: str
    environment: str
    production: bool | None
    status: str
    started_at: datetime
    occurred_at: datetime


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def github_deployment(kind: str, payload: dict[str, Any]) -> DeploymentFact | None:
    if kind not in {"deployment", "deployment_status"}:
        return None
    deployment = payload.get("deployment")
    status = payload.get("deployment_status") if kind == "deployment_status" else deployment
    if not isinstance(deployment, dict) or not isinstance(status, dict):
        return None
    deployment_id, observation_id = deployment.get("id"), status.get("id")
    sha, environment = (
        deployment.get("sha"),
        status.get("environment") or deployment.get("environment"),
    )
    started, occurred = (
        _timestamp(deployment.get("created_at")),
        _timestamp(status.get("created_at")),
    )
    state = status.get("state", "").upper() if isinstance(status.get("state", ""), str) else ""
    if kind == "deployment":
        state = "CREATED"
    if (
        type(deployment_id) is not int
        or not 0 < deployment_id <= 2**63 - 1
        or type(observation_id) is not int
        or not 0 < observation_id <= 2**63 - 1
        or not isinstance(sha, str)
        or not re.fullmatch(r"[0-9a-f]{40,64}", sha)
        or not isinstance(environment, str)
        or not 0 < len(environment) <= 255
        or any(ord(char) < 32 for char in environment)
        or started is None
        or occurred is None
        or occurred < started
        or state not in DEPLOYMENT_STATUSES
    ):
        return None
    production = deployment.get("production_environment")
    return DeploymentFact(
        str(deployment_id),
        "created" if kind == "deployment" else str(observation_id),
        sha,
        environment,
        production if type(production) is bool else None,
        state,
        started,
        occurred,
    )
