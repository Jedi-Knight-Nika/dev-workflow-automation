"""Framework-independent semantic decisions; resource authority stays in code."""

from dataclasses import dataclass
from enum import StrEnum


class Directive(StrEnum):
    WAIT = "WAIT"
    REPLY = "REPLY"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    UPDATE_SUMMARY = "UPDATE_SUMMARY"
    SYNC_STATUS = "SYNC_STATUS"
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    ASK_HUMAN = "ASK_HUMAN"
    IMPLEMENT = "IMPLEMENT"
    REPAIR = "REPAIR"
    PAUSE = "PAUSE"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class Checkpoint:
    goal: str
    invariants: tuple[str, ...]
    open_questions: tuple[str, ...]


@dataclass(frozen=True)
class Decision:
    version: int
    action: Directive
    message: str
    engineering_request: str
    reason: str
    choices: tuple[str, ...]
    read_tools: tuple[str, ...]
    checkpoint: Checkpoint


def validate_effect(
    decision: Decision,
    *,
    status: str,
    manual_takeover: bool,
    expected_revision: int,
    current_revision: int,
    expected_requirement: int,
    current_requirement: int,
    human_continuation: bool = False,
    engineering_event: bool = False,
) -> None:
    if (expected_revision, expected_requirement) != (current_revision, current_requirement):
        raise ValueError("Task changed after this decision")
    if manual_takeover:
        raise ValueError("Manual takeover owns this task")
    if engineering_event and decision.action not in {Directive.WAIT, Directive.REPLY}:
        raise ValueError("Engineering notifications cannot dispatch competing work")
    if status in {"MERGED", "FAILED", "CANCELLED", "PAUSED"} and decision.action not in {
        Directive.WAIT,
        Directive.REPLY,
    }:
        raise ValueError("Suspended or terminal tasks require explicit operator control")
    if (
        status == "WAITING_HUMAN"
        and not human_continuation
        and decision.action not in {Directive.WAIT, Directive.REPLY}
    ):
        raise ValueError("Resolve the current human request first")
