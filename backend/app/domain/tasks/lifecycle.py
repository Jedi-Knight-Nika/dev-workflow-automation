from dataclasses import dataclass
from enum import StrEnum

from app.domain.tasks.entities import TaskState


class LifecycleAction(StrEnum):
    PAUSE = "PAUSE"
    CANCEL = "CANCEL"
    TAKEOVER = "TAKEOVER"
    RESUME = "RESUME"
    ARCHIVE = "ARCHIVE"


class InvalidTaskTransition(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LifecycleDirective:
    state: TaskState
    manual_takeover: bool
    cancel_queued_jobs: bool = False
    archive: bool = False


def lifecycle_directive(
    action: LifecycleAction,
    *,
    current_state: TaskState,
    manual_takeover: bool,
    has_pull_request: bool,
) -> LifecycleDirective:
    if action == LifecycleAction.PAUSE:
        return LifecycleDirective(TaskState.PAUSED, manual_takeover)
    if action == LifecycleAction.CANCEL:
        return LifecycleDirective(TaskState.CANCELLED, manual_takeover, True)
    if action == LifecycleAction.ARCHIVE:
        if current_state not in {TaskState.CANCELLED, TaskState.FAILED, TaskState.MERGED}:
            raise InvalidTaskTransition("Only terminal tasks can be archived")
        return LifecycleDirective(current_state, False, True, True)
    if action == LifecycleAction.TAKEOVER:
        if current_state in {TaskState.CANCELLED, TaskState.MERGED}:
            raise InvalidTaskTransition(f"Cannot take over a {current_state.value} task")
        return LifecycleDirective(TaskState.PAUSED, True, True)
    if not manual_takeover:
        raise InvalidTaskTransition("Task is not under manual control")
    return LifecycleDirective(
        TaskState.WAITING_GITHUB if has_pull_request else TaskState.LOCAL_VALIDATION,
        False,
    )
