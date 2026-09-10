from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.engineering.infrastructure.job_queue import claim_next_job
from app.engineering.infrastructure.task_models import Job
from app.platform.scheduling.states import JobState


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,occupied,paused,claimed",
    [
        ("RUN_VALIDATION", 1, False, True),
        ("PUBLISH_PR", 1, False, True),
        ("MERGE_PR", 1, False, True),
        ("DEVELOPER_TURN", 1, False, False),
        ("DEVELOPER_TURN", 0, False, True),
        ("PUBLISH_PR", 1, True, False),
    ],
)
async def test_capacity_only_blocks_slot_consuming_jobs(action, occupied, paused, claimed):
    job = Job(id=uuid4(), task_id=uuid4(), action=action, state=JobState.QUEUED, attempt=0)
    task = SimpleNamespace(team_id=uuid4())
    team = SimpleNamespace(
        enabled=True, execution_paused=paused, archived_at=None, max_concurrent_tasks=1
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[job, occupied]),
        get=AsyncMock(side_effect=[task, team]),
        get_bind=Mock(return_value=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))),
        add=Mock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    result = await claim_next_job(session, "worker", 60)
    assert (result is job) == claimed
    assert session.commit.await_count == int(claimed)
    assert session.rollback.await_count == int(not claimed)
    assert job.state == (JobState.CLAIMED if claimed else JobState.QUEUED)
    sql = str(
        session.scalar.call_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "jobs.action NOT IN" in sql
    assert "INTERPRET_EVENT" in sql and "DEVELOPER_TURN" in sql
    assert "NOT (EXISTS" in sql  # Same-task exclusion remains in the claim query.
