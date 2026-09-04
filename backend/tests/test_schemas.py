import uuid

import pytest
from pydantic import ValidationError

from app.db.models import JobRole
from app.schemas import TaskCreate, WorkerResult


def test_task_priority_is_bounded():
    with pytest.raises(ValidationError):
        TaskCreate(title="x", priority=6)


def test_worker_result_protocol():
    result = WorkerResult(
        job_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        role=JobRole.THINKER,
        result="PLAN_READY",
        summary="done",
    )
    assert result.protocol_version == 1
    assert result.data == {}
