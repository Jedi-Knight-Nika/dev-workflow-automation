from dataclasses import dataclass, replace
from enum import StrEnum


class TaskStatus(StrEnum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    WAITING_HUMAN = "WAITING_HUMAN"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    MERGED = "MERGED"


class Stage(StrEnum):
    INTAKE = "INTAKE"
    PLANNING = "PLANNING"
    DEVELOPING = "DEVELOPING"
    VALIDATING = "VALIDATING"
    PUBLISHING = "PUBLISHING"
    REVIEWING = "REVIEWING"
    FIXING = "FIXING"
    MERGING = "MERGING"
    COMPLETE = "COMPLETE"


class WaitReason(StrEnum):
    NONE = "NONE"
    GITHUB_REVIEW = "GITHUB_REVIEW"
    GITHUB_CHECKS = "GITHUB_CHECKS"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_OUTAGE = "PROVIDER_OUTAGE"
    INTEGRATION_FAILURE = "INTEGRATION_FAILURE"
    MISSING_CONFIGURATION = "MISSING_CONFIGURATION"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    MISSING_REQUIREMENT = "MISSING_REQUIREMENT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    MERGE_CONFLICT = "MERGE_CONFLICT"
    MANUAL_TAKEOVER = "MANUAL_TAKEOVER"


class Action(StrEnum):
    START = "START"
    NEEDS_PLAN = "NEEDS_PLAN"
    PLAN_READY = "PLAN_READY"
    IMPLEMENTED = "IMPLEMENTED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PUBLISHED = "PUBLISHED"
    REVIEW_FIX = "REVIEW_FIX"
    REQUIREMENT_CHANGED = "REQUIREMENT_CHANGED"
    REVISE_REQUIREMENT = "REVISE_REQUIREMENT"
    MERGE_AUTHORIZED = "MERGE_AUTHORIZED"
    MERGE_RECHECK = "MERGE_RECHECK"
    MERGED = "MERGED"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"
    TAKEOVER = "TAKEOVER"
    RELEASE_TAKEOVER = "RELEASE_TAKEOVER"
    BLOCK = "BLOCK"


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True)
class EngineeringState:
    status: TaskStatus = TaskStatus.NEW
    stage: Stage = Stage.INTAKE
    wait_reason: WaitReason = WaitReason.NONE
    requirement_version: int = 1
    manual_takeover: bool = False

    def __post_init__(self) -> None:
        if self.requirement_version < 1:
            raise ValueError("Requirement version must be positive")
        if (
            self.status in {TaskStatus.NEW, TaskStatus.ACTIVE, TaskStatus.MERGED}
            and self.wait_reason != WaitReason.NONE
        ):
            raise ValueError("Runnable/completed state cannot have a wait reason")
        if (
            self.status in {TaskStatus.WAITING_EXTERNAL, TaskStatus.WAITING_HUMAN}
            and self.wait_reason == WaitReason.NONE
        ):
            raise ValueError("Waiting state requires a reason")
        if (self.status == TaskStatus.MERGED) != (self.stage == Stage.COMPLETE):
            raise ValueError("Only merged tasks can be complete")
        if self.manual_takeover and self.status != TaskStatus.PAUSED:
            raise ValueError("Manual takeover requires a paused task")


_STEPS = {
    Action.START: ({Stage.INTAKE}, Stage.DEVELOPING),
    Action.NEEDS_PLAN: ({Stage.DEVELOPING, Stage.FIXING}, Stage.PLANNING),
    Action.PLAN_READY: ({Stage.PLANNING}, Stage.DEVELOPING),
    Action.IMPLEMENTED: ({Stage.DEVELOPING, Stage.FIXING}, Stage.VALIDATING),
    Action.VALIDATION_FAILED: ({Stage.VALIDATING}, Stage.FIXING),
    Action.VALIDATION_PASSED: ({Stage.VALIDATING}, Stage.PUBLISHING),
    Action.PUBLISHED: ({Stage.PUBLISHING}, Stage.REVIEWING),
    Action.REVIEW_FIX: ({Stage.REVIEWING}, Stage.FIXING),
    Action.MERGE_AUTHORIZED: ({Stage.REVIEWING}, Stage.MERGING),
    Action.MERGE_RECHECK: ({Stage.MERGING}, Stage.REVIEWING),
    Action.MERGED: ({Stage.MERGING}, Stage.COMPLETE),
}


def transition(
    state: EngineeringState,
    action: Action,
    *,
    wait_reason: WaitReason = WaitReason.NONE,
    external_wait: bool = False,
) -> EngineeringState:
    """A fixed business transition; no model result grants merge authority here.

    Callers must authorize MERGE_AUTHORIZED using Delivery policy and persist the
    transition with optimistic/lease checks. Resume retains the current stage.
    """
    if state.status in {TaskStatus.MERGED, TaskStatus.CANCELLED, TaskStatus.FAILED}:
        raise InvalidTransition("Terminal tasks cannot be implicitly reopened")
    if action == Action.CANCEL:
        return replace(state, status=TaskStatus.CANCELLED, manual_takeover=False)
    if action in {Action.PAUSE, Action.TAKEOVER}:
        takeover = action == Action.TAKEOVER or state.manual_takeover
        return replace(
            state,
            status=TaskStatus.PAUSED,
            manual_takeover=takeover,
            wait_reason=WaitReason.MANUAL_TAKEOVER if takeover else state.wait_reason,
        )
    if action == Action.REVISE_REQUIREMENT:
        if state.status != TaskStatus.PAUSED:
            raise InvalidTransition("Pause work before revising a requirement")
        return replace(
            state,
            stage=Stage.INTAKE if state.stage == Stage.INTAKE else Stage.FIXING,
            requirement_version=state.requirement_version + 1,
        )
    if action in {Action.RESUME, Action.RELEASE_TAKEOVER}:
        if state.status not in {
            TaskStatus.PAUSED,
            TaskStatus.WAITING_HUMAN,
            TaskStatus.WAITING_EXTERNAL,
        }:
            raise InvalidTransition("Only suspended work can resume")
        if state.manual_takeover and action != Action.RELEASE_TAKEOVER:
            raise InvalidTransition("Release manual takeover explicitly")
        reviewing = state.stage == Stage.REVIEWING
        return replace(
            state,
            status=TaskStatus.WAITING_EXTERNAL if reviewing else TaskStatus.ACTIVE,
            wait_reason=WaitReason.GITHUB_REVIEW if reviewing else WaitReason.NONE,
            manual_takeover=False,
        )
    if state.status == TaskStatus.PAUSED or state.manual_takeover:
        raise InvalidTransition("Paused work cannot advance")
    if action == Action.BLOCK:
        if wait_reason == WaitReason.NONE:
            raise InvalidTransition("A blocker must state its reason")
        return replace(
            state,
            status=TaskStatus.WAITING_EXTERNAL if external_wait else TaskStatus.WAITING_HUMAN,
            wait_reason=wait_reason,
        )
    if state.status == TaskStatus.WAITING_HUMAN:
        raise InvalidTransition("Resolve the human blocker before advancing")
    if action == Action.REQUIREMENT_CHANGED:
        return replace(
            state,
            status=TaskStatus.ACTIVE,
            stage=Stage.FIXING,
            wait_reason=WaitReason.NONE,
            requirement_version=state.requirement_version + 1,
        )
    permitted, target = _STEPS[action]
    if state.stage not in permitted:
        raise InvalidTransition(f"{action.value} cannot follow {state.stage.value}")
    if state.status == TaskStatus.WAITING_EXTERNAL and action not in {
        Action.REVIEW_FIX,
        Action.MERGE_AUTHORIZED,
    }:
        raise InvalidTransition("An external wait must be resolved before advancing")
    status = TaskStatus.ACTIVE
    reason = WaitReason.NONE
    if action in {Action.PUBLISHED, Action.MERGE_RECHECK}:
        status, reason = TaskStatus.WAITING_EXTERNAL, WaitReason.GITHUB_REVIEW
    elif action == Action.MERGED:
        status = TaskStatus.MERGED
    return replace(state, status=status, stage=target, wait_reason=reason)
