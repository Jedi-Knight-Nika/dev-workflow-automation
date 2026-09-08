from decimal import Decimal
from uuid import uuid4

import pytest

from app.engineering.domain.lifecycle import Action, EngineeringState, TaskStatus, transition
from app.teams.domain.automation import AutomationPolicy


def test_automation_defaults_never_authorize_enrollment_or_merge() -> None:
    policy = AutomationPolicy()
    assert not policy.enrollment_enabled and not policy.auto_merge


@pytest.mark.parametrize(
    "values",
    [
        {"enrollment_enabled": True},
        {"auto_merge": True},
        {"authorized_reviewer_ids": ("a-login",)},
        {"task_budget_usd": Decimal(21), "team_budget_usd": Decimal(20)},
    ],
)
def test_policy_rejects_ambiguous_authority_and_invalid_budgets(values: dict) -> None:
    with pytest.raises(ValueError):
        AutomationPolicy(**values)


def test_policy_allows_explicit_scoped_rollout() -> None:
    assert AutomationPolicy(
        enrollment_enabled=True,
        repository_ids=(uuid4(),),
        auto_merge=True,
        required_checks=("test",),
        authorized_reviewer_ids=("123",),
    ).auto_merge


def test_any_human_policy_does_not_require_an_allowlist_but_still_requires_ci() -> None:
    assert AutomationPolicy(
        auto_merge=True,
        reviewer_scope="any_human",
        require_formal_approval=False,
        required_checks=("test",),
    ).auto_merge
    with pytest.raises(ValueError):
        AutomationPolicy(auto_merge=True, reviewer_scope="any_human")
    with pytest.raises(ValueError):
        AutomationPolicy(reviewer_scope="anyone_including_bots")


def test_fixed_pipeline_can_repair_review_and_finish_without_replanning() -> None:
    state = EngineeringState()
    for action in (
        Action.START,
        Action.IMPLEMENTED,
        Action.VALIDATION_FAILED,
        Action.IMPLEMENTED,
        Action.VALIDATION_PASSED,
        Action.PUBLISHED,
    ):
        state = transition(state, action)
    assert state.status == TaskStatus.WAITING_EXTERNAL
    for action in (
        Action.REVIEW_FIX,
        Action.IMPLEMENTED,
        Action.VALIDATION_PASSED,
        Action.PUBLISHED,
        Action.MERGE_AUTHORIZED,
        Action.MERGED,
    ):
        state = transition(state, action)
    assert state.status == TaskStatus.MERGED
