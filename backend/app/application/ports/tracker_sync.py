import uuid
from typing import Protocol


class TrackerTaskNotFound(Exception):
    pass


class TrackerSyncConflict(Exception):
    pass


class TrackerSyncWorkflow(Protocol):
    async def synchronize_merged_task(self, task_id: uuid.UUID) -> bool: ...
