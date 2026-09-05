import uuid

import pytest

from app.application.tasks import SynchronizeMergedTask


class FakeTrackerSyncWorkflow:
    def __init__(self, synchronized: bool) -> None:
        self.synchronized = synchronized
        self.task_id: uuid.UUID | None = None

    async def synchronize_merged_task(self, task_id: uuid.UUID) -> bool:
        self.task_id = task_id
        return self.synchronized


@pytest.mark.asyncio
async def test_synchronize_merged_task_delegates_through_port() -> None:
    task_id = uuid.uuid4()
    workflow = FakeTrackerSyncWorkflow(True)

    assert await SynchronizeMergedTask(workflow).execute(task_id)
    assert workflow.task_id == task_id
