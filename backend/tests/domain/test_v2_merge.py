from dataclasses import replace

import pytest

from app.delivery.domain.merge import Approval, MergeEvidence, MergePolicy


def valid() -> tuple[MergePolicy, MergeEvidence]:
    return (
        MergePolicy(True, True, frozenset({"alice"})),
        MergeEvidence(
            "a" * 40,
            "a" * 40,
            "a" * 40,
            True,
            True,
            True,
            False,
            True,
            True,
            Approval("alice", "a" * 40, "review-123"),
        ),
    )


def test_merge_requires_all_current_evidence() -> None:
    policy, evidence = valid()
    assert policy.blockers(evidence) == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"current_sha": "b" * 40},
        {"validated_sha": "b" * 40},
        {"pr_open": False},
        {"checks_complete": False},
        {"checks_passed": False},
        {"blocking_review": True},
        {"mergeable": None},
        {"task_runnable": False},
        {"approval": None},
        {"approval": Approval("mallory", "a" * 40, "review-1")},
        {"approval": Approval("alice", "b" * 40, "review-2")},
        {"approval": Approval("alice", "a" * 40, "comment-lgtm", False)},
    ],
)
def test_merge_fails_closed(changes: dict) -> None:
    policy, evidence = valid()
    assert policy.blockers(replace(evidence, **changes))


def test_auto_merge_is_opt_in_for_both_team_and_repository() -> None:
    policy, evidence = valid()
    assert replace(policy, team_auto_merge=False).blockers(evidence)
    assert replace(policy, repository_auto_merge=False).blockers(evidence)
