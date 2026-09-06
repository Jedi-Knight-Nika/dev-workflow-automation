import uuid
from typing import Any, cast

import pytest

from app.application.ports.job_dispatch import ClaimedJob
from app.domain.operational_states import JobRole
from app.infrastructure.scheduler import Scheduler


class PreparedDispatch:
    async def prepare(self, _job: ClaimedJob) -> bool:
        return True


class ForbiddenRunner:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, _job_id: uuid.UUID) -> None:
        self.called = True
        raise AssertionError("A durable result must not launch another worker")


class RecordingCompleter:
    def __init__(self) -> None:
        self.commands: list[object] = []

    async def execute(self, command: object) -> bool:
        self.commands.append(command)
        return True


@pytest.mark.asyncio
async def test_reclaimed_job_resumes_durable_result_without_worker_execution() -> None:
    job_id = uuid.uuid4()
    task_id = uuid.uuid4()
    lease_token = uuid.uuid4()
    runner = ForbiddenRunner()
    executor_completer = RecordingCompleter()
    unused = cast(Any, object())
    scheduler = Scheduler(
        unused,
        "test-scheduler",
        cast(Any, PreparedDispatch()),
        cast(Any, runner),
        unused,
        unused,
        unused,
        cast(Any, executor_completer),
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
    )
    claimed = ClaimedJob(
        job_id,
        lease_token,
        {
            "protocol_version": 1,
            "job_id": str(job_id),
            "task_id": str(task_id),
            "role": JobRole.EXECUTOR.value,
            "result": "IMPLEMENTED",
            "summary": "Already completed",
            "data": {"changed_files": ["src/example.py"]},
        },
    )

    await scheduler._execute(claimed)

    assert not runner.called
    assert len(executor_completer.commands) == 1
