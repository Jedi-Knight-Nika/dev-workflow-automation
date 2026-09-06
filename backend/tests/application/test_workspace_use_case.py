import uuid
from datetime import UTC, datetime

import pytest

from app.application.tasks import PrepareTaskWorkspace
from app.domain.tasks import Task, TaskState


class FakeWorkspaceWorkflow:
    def __init__(self, task: Task) -> None:
        self.task = task
        self.prepared_id: uuid.UUID | None = None

    async def prepare(self, task_id: uuid.UUID) -> Task:
        self.prepared_id = task_id
        return self.task


@pytest.mark.asyncio
async def test_prepare_workspace_delegates_through_application_port() -> None:
    now = datetime.now(UTC)
    task = Task(
        uuid.uuid4(),
        "Prepare workspace",
        "",
        3,
        TaskState.PLANNING,
        None,
        uuid.uuid4(),
        "abc123",
        "task/branch",
        "/workspace",
        None,
        None,
        False,
        now,
        now,
    )
    workflow = FakeWorkspaceWorkflow(task)

    result = await PrepareTaskWorkspace(workflow).execute(task.id)

    assert result is task
    assert workflow.prepared_id == task.id
