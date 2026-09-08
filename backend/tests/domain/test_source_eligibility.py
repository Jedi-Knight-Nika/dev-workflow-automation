import pytest

from app.delivery.domain.status import semantic_status
from app.intake.domain.eligibility import linear_eligible


def test_linear_eligibility_uses_explicit_assignment_and_state_only() -> None:
    config = {"assignee_id": "operator", "source_state_ids": ["ready"]}
    assert linear_eligible(config, "operator", "ready")
    assert not linear_eligible(config, "other", "ready")
    assert not linear_eligible(config, "operator", "done")
    assert not linear_eligible({}, "operator", "ready")
    assert not linear_eligible({**config, "source_state_ids": "ready"}, "operator", "ready")


@pytest.mark.parametrize(
    ("status", "stage", "expected"),
    [
        ("MERGED", "COMPLETE", "done"),
        ("CANCELLED", "DEVELOPING", "cancelled"),
        ("WAITING_HUMAN", "FIXING", "blocked"),
        ("PAUSED", "DEVELOPING", "paused"),
        ("WAITING_EXTERNAL", "REVIEWING", "in_review"),
        ("ACTIVE", "VALIDATING", "in_progress"),
        ("NEW", "INTAKE", "todo"),
    ],
)
def test_tracker_semantics_do_not_report_cancelled_or_paused_as_done(
    status: str, stage: str, expected: str
) -> None:
    assert semantic_status(status, stage) == expected
