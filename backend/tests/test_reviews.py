import uuid

from app.db.models import Job, JobRole
from app.infrastructure.persistence.reviews import finding_fingerprint, reviewer_fingerprint


def test_reviewer_uses_executor_workspace_fingerprint() -> None:
    job = Job(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        role=JobRole.REVIEWER,
        action="REVIEW_CHANGES",
        payload={"data": {"workspace_fingerprint": "abc123"}},
    )

    assert reviewer_fingerprint(job) == "abc123"


def test_finding_fingerprint_normalizes_case_and_whitespace() -> None:
    first = finding_fingerprint(
        {"severity": "high", "path": "src/a.py", "line": 4, "message": "Null   crash"}
    )
    second = finding_fingerprint(
        {"severity": "HIGH", "path": "src/a.py", "line": 4, "message": "null crash"}
    )

    assert first == second
