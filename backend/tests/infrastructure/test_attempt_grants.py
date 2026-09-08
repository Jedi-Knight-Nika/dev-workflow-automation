import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.db.models import Job, Task, TaskEvent
from app.infrastructure.workers.attempt_grants import grant_limits
from app.worker import BudgetExceeded, enforce_spending_budget


def fixture():
    job = Job(id=uuid.uuid4(), task_id=uuid.uuid4())
    payload = {
        "job_id": str(job.id),
        "approved_by": "user",
        "baseline_tokens": 365201,
        "baseline_calls": 25,
        "additional_tokens": 120000,
        "additional_calls": 8,
    }
    return job, payload


def test_grant_is_job_scoped_and_keeps_absolute_history():
    job, payload = fixture()
    assert grant_limits(payload, job, 120000, 8) == (485201, 33)
    assert grant_limits(payload, Job(id=uuid.uuid4()), 120000, 8) is None


@pytest.mark.parametrize(
    "change",
    [
        {"additional_tokens": 120001},
        {"additional_calls": 9},
        {"baseline_tokens": -1},
        {"additional_tokens": True},
        {"approved_by": "agent"},
        {"baseline_calls": None},
    ],
)
def test_invalid_grants_are_ignored(change):
    job, payload = fixture()
    assert grant_limits({**payload, **change}, job, 120000, 8) is None


@pytest.mark.asyncio
async def test_grant_changes_only_task_guard_not_job_guard():
    job, payload = fixture()
    session = AsyncMock()
    session.get.return_value = None
    session.scalar.return_value = TaskEvent(payload=payload)
    session.execute.side_effect = [
        SimpleNamespace(one=lambda: (0, 0, 0)),
        SimpleNamespace(one=lambda: (365201, 0, 25)),
    ]
    task = Task(id=job.task_id, team_id=None)
    await enforce_spending_budget(
        session, job, task, Settings(_env_file=None), {}, [], reserved_tokens=10000
    )
    session.execute.side_effect = [SimpleNamespace(one=lambda: (120000, 0, 7))]
    with pytest.raises(BudgetExceeded, match="Job token budget exhausted"):
        await enforce_spending_budget(session, job, task, Settings(_env_file=None), {}, [])
    session.execute.side_effect = [
        SimpleNamespace(one=lambda: (100000, 0, 7)),
        SimpleNamespace(one=lambda: (485201, 0, 32)),
    ]
    with pytest.raises(BudgetExceeded, match="Task token budget exhausted"):
        await enforce_spending_budget(session, job, task, Settings(_env_file=None), {}, [])
