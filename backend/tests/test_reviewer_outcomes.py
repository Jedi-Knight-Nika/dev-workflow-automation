import pytest
from pydantic import ValidationError

from app.infrastructure.workers.executor import ReviewerProposal


def test_reviewer_pass_rejects_findings() -> None:
    with pytest.raises(ValidationError, match="PASS must not include findings"):
        ReviewerProposal(
            result="PASS",
            summary="Contradictory",
            findings=[{"severity": "HIGH", "message": "Still broken"}],
        )


def test_reviewer_failure_requires_actionable_finding() -> None:
    with pytest.raises(ValidationError, match="requires at least one finding"):
        ReviewerProposal(result="FAIL_ACTIONABLE", summary="Broken")


def test_reviewer_uncertainty_requires_reason() -> None:
    with pytest.raises(ValidationError, match="requires a reason"):
        ReviewerProposal(result="UNCERTAIN", summary="Cannot establish correctness")


def test_reviewer_accepts_architectural_failure() -> None:
    review = ReviewerProposal(
        result="FAIL_ARCHITECTURAL",
        summary="Invariant conflict",
        findings=[{"severity": "HIGH", "message": "Current plan violates immutability"}],
    )
    assert review.result == "FAIL_ARCHITECTURAL"
