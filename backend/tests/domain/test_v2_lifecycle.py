from dataclasses import replace

import pytest

from app.engineering.domain.lifecycle import (
    Action,
    EngineeringState,
    InvalidTransition,
    Stage,
    TaskStatus,
    WaitReason,
    transition,
)


def test_happy_path_waits_without_replanning() -> None:
    state = EngineeringState()
    for action in (Action.START, Action.IMPLEMENTED, Action.VALIDATION_PASSED, Action.PUBLISHED):
        state = transition(state, action)
    assert state == EngineeringState(
        TaskStatus.WAITING_EXTERNAL, Stage.REVIEWING, WaitReason.GITHUB_REVIEW
    )
    state = transition(state, Action.REVIEW_FIX)
    assert state.stage == Stage.FIXING
    for action in (
        Action.IMPLEMENTED,
        Action.VALIDATION_PASSED,
        Action.PUBLISHED,
        Action.MERGE_AUTHORIZED,
        Action.MERGED,
    ):
        state = transition(state, action)
    assert state.status == TaskStatus.MERGED
    assert state.stage == Stage.COMPLETE


def test_validation_failure_returns_to_same_development_stage() -> None:
    state = EngineeringState(TaskStatus.ACTIVE, Stage.VALIDATING)
    assert transition(state, Action.VALIDATION_FAILED).stage == Stage.FIXING


def test_resume_does_not_reset_stage_or_requirement_version() -> None:
    state = EngineeringState(TaskStatus.ACTIVE, Stage.FIXING, requirement_version=7)
    assert transition(transition(state, Action.PAUSE), Action.RESUME) == state


def test_takeover_requires_explicit_release() -> None:
    state = transition(EngineeringState(TaskStatus.ACTIVE, Stage.DEVELOPING), Action.TAKEOVER)
    with pytest.raises(InvalidTransition, match="Release"):
        transition(state, Action.RESUME)
    assert not transition(state, Action.RELEASE_TAKEOVER).manual_takeover


@pytest.mark.parametrize("action", [Action.IMPLEMENTED, Action.MERGE_AUTHORIZED, Action.MERGED])
def test_paused_work_cannot_advance(action: Action) -> None:
    with pytest.raises(InvalidTransition):
        transition(EngineeringState(TaskStatus.PAUSED, Stage.DEVELOPING), action)


@pytest.mark.parametrize("status", [TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.MERGED])
def test_terminal_work_cannot_implicitly_reopen(status: TaskStatus) -> None:
    state = EngineeringState(
        status, Stage.COMPLETE if status == TaskStatus.MERGED else Stage.DEVELOPING
    )
    with pytest.raises(InvalidTransition):
        transition(state, Action.RESUME)


def test_provider_wait_resumes_in_place() -> None:
    before = EngineeringState(TaskStatus.ACTIVE, Stage.DEVELOPING)
    waiting = transition(
        before, Action.BLOCK, wait_reason=WaitReason.PROVIDER_RATE_LIMIT, external_wait=True
    )
    assert transition(waiting, Action.RESUME) == before


def test_new_requirement_versions_feedback_without_erasing_history() -> None:
    before = EngineeringState(
        TaskStatus.WAITING_EXTERNAL, Stage.REVIEWING, WaitReason.GITHUB_REVIEW, 4
    )
    after = transition(before, Action.REQUIREMENT_CHANGED)
    assert after.requirement_version == 5
    assert after.stage == Stage.FIXING
    assert before.requirement_version == 4


def test_invalid_state_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(EngineeringState(), stage=Stage.COMPLETE)
    with pytest.raises(ValueError):
        replace(EngineeringState(), status=TaskStatus.WAITING_HUMAN)
