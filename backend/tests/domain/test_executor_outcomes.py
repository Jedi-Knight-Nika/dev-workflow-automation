import pytest
from pydantic import ValidationError

from app.infrastructure.workers.executor import ExecutorProposal


def test_executor_plan_mismatch_requires_details() -> None:
    with pytest.raises(ValidationError, match="plan_mismatch details"):
        ExecutorProposal(result="PLAN_MISMATCH", summary="Cannot proceed")


def test_executor_nonimplementation_cannot_smuggle_file_changes() -> None:
    with pytest.raises(ValidationError, match="must not include file changes"):
        ExecutorProposal(
            result="NEEDS_HUMAN",
            summary="Needs a decision",
            reason="Ambiguous invariant",
            files=[{"path": "unsafe.py", "content": "changed = True"}],
        )


def test_executor_accepts_bounded_replan_outcome() -> None:
    proposal = ExecutorProposal(
        result="NEEDS_REPLAN",
        summary="Repository differs from plan",
        plan_mismatch="The planned module was removed",
    )
    assert proposal.files == []


def test_executor_context_request_requires_explicit_paths() -> None:
    with pytest.raises(ValidationError, match="requires requested_files"):
        ExecutorProposal(result="REQUEST_CONTEXT", summary="Need source")


def test_executor_accepts_bounded_context_request() -> None:
    proposal = ExecutorProposal(
        result="REQUEST_CONTEXT",
        summary="Need the Team model",
        requested_files=["backend/app/db/models/teams.py"],
    )

    assert proposal.requested_files == ["backend/app/db/models/teams.py"]
