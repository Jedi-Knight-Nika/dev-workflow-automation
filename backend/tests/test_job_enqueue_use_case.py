import uuid
from datetime import UTC, datetime

import pytest

from app.application.jobs import EnqueueTaskJob
from app.application.ports.job_enqueueing import EnqueuedJob, EnqueueJobCommand


class FakeJobEnqueueWorkflow:
    def __init__(self, job: EnqueuedJob) -> None:
        self.job = job
        self.command: EnqueueJobCommand | None = None

    async def enqueue(self, command: EnqueueJobCommand) -> EnqueuedJob:
        self.command = command
        return self.job


@pytest.mark.asyncio
async def test_enqueue_task_job_delegates_typed_command() -> None:
    now = datetime.now(UTC)
    task_id = uuid.uuid4()
    job = EnqueuedJob(
        uuid.uuid4(),
        task_id,
        "EXECUTOR",
        "REPAIR_LOCAL_VALIDATION",
        2,
        "QUEUED",
        0,
        {"reason": "test"},
        None,
        None,
        None,
        None,
        now,
        None,
        None,
    )
    workflow = FakeJobEnqueueWorkflow(job)
    command = EnqueueJobCommand(
        task_id, "EXECUTOR", "REPAIR_LOCAL_VALIDATION", 2, {"reason": "test"}
    )

    result = await EnqueueTaskJob(workflow).execute(command)

    assert result is job
    assert workflow.command == command
