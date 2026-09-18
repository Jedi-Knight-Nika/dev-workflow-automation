"""Typed work/result contracts shared by the controller and isolated runner."""

from enum import StrEnum
from typing import Any
from uuid import UUID

from app.agent_runtime.domain.envelope import AgentEnvelope


class WorkOutcome(StrEnum):
    IMPLEMENTED = "IMPLEMENTED"
    NEEDS_PLAN = "NEEDS_PLAN"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    MILESTONE_COMPLETE = "MILESTONE_COMPLETE"
    FAILED = "FAILED"


def work_packet(
    task_id: UUID,
    revision: int,
    sha: str | None,
    request: str,
    *,
    repair: bool = False,
    invariants: tuple[str, ...] = (),
) -> AgentEnvelope:
    if not request.strip() or len(request) > 24000:
        raise ValueError("Work needs a complete bounded request")
    if len(invariants) > 8 or any(
        not isinstance(item, str) or len(item) > 600 for item in invariants
    ):
        raise ValueError("Work invariants exceed their bounds")
    return AgentEnvelope(
        1,
        "repair" if repair else "work",
        task_id,
        revision,
        sha,
        {"request": request, "invariants": list(invariants)},
    )


def validate_work(packet: AgentEnvelope) -> None:
    if packet.type not in {"work", "repair"} or set(packet.payload) != {"request", "invariants"}:
        raise ValueError("Invalid work contract")
    if not isinstance(packet.payload["request"], str) or not isinstance(
        packet.payload["invariants"], list
    ):
        raise TypeError("Invalid work payload types")
    work_packet(
        packet.task_id,
        packet.requirement_revision,
        packet.current_sha,
        packet.payload["request"],
        invariants=tuple(packet.payload["invariants"]),
    )


def validate_result(packet: AgentEnvelope, work: AgentEnvelope) -> WorkOutcome:
    if packet.type != "result" or (
        packet.task_id,
        packet.requirement_revision,
        packet.current_sha,
    ) != (
        work.task_id,
        work.requirement_revision,
        work.current_sha,
    ):
        raise ValueError("Result belongs to a different task, requirement or input SHA")
    if set(packet.payload) != {"outcome", "summary", "failure_code", "checks", "turn_id"}:
        raise ValueError("Invalid result contract")
    if not isinstance(packet.payload["summary"], str) or len(packet.payload["summary"]) > 8000:
        raise ValueError("Invalid result summary")
    if not isinstance(packet.payload["turn_id"], str) or not packet.payload["turn_id"]:
        raise ValueError("Result requires its receipt identity")
    failure = packet.payload["failure_code"]
    if failure is not None and (not isinstance(failure, str) or len(failure) > 200):
        raise ValueError("Invalid result failure code")
    checks = packet.payload["checks"]
    if (
        not isinstance(checks, list)
        or len(checks) > 100
        or any(
            not isinstance(check, dict)
            or set(check) != {"name", "status"}
            or not isinstance(check["name"], str)
            or len(check["name"]) > 200
            or check["status"] not in {"PASSED", "FAILED", "UNKNOWN"}
            for check in checks
        )
    ):
        raise ValueError("Invalid check evidence")
    return WorkOutcome(packet.payload["outcome"])


def result_packet(
    work: AgentEnvelope,
    *,
    status: str,
    summary: str,
    turn_id: str,
    failure_code: str | None,
    checks: list[dict[str, Any]],
) -> AgentEnvelope:
    # Legacy native SDK text is normalized only at the runner boundary. Controllers
    # consume the typed outcome. A prose success claim cannot bypass full validation.
    first = summary.strip().split("\n", 1)[0].strip()
    outcome = (
        WorkOutcome.FAILED
        if status != "completed"
        else (WorkOutcome(first) if first in set(WorkOutcome) else WorkOutcome.NEEDS_HUMAN)
    )
    packet = AgentEnvelope(
        1,
        "result",
        work.task_id,
        work.requirement_revision,
        work.current_sha,
        {
            "outcome": outcome.value,
            "summary": summary[-8000:],
            "failure_code": failure_code,
            "turn_id": turn_id,
            "checks": checks[:100],
        },
        (turn_id,),
    )
    validate_result(packet, work)
    return packet
