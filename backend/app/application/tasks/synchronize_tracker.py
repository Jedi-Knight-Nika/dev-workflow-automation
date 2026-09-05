import uuid

from app.application.ports.tracker_sync import TrackerSyncWorkflow


class SynchronizeMergedTask:
    def __init__(self, workflow: TrackerSyncWorkflow) -> None:
        self._workflow = workflow

    async def execute(self, task_id: uuid.UUID) -> bool:
        return await self._workflow.synchronize_merged_task(task_id)
