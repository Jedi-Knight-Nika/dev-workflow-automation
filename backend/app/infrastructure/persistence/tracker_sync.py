import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.tracker_sync import TrackerSyncConflict, TrackerTaskNotFound
from app.db.models import Task, TaskState
from app.infrastructure.linear_sync import sync_merged_task_to_linear


class SqlAlchemyLinearSyncWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def synchronize_merged_task(self, task_id: uuid.UUID) -> bool:
        task = await self._session.get(Task, task_id)
        if task is None:
            raise TrackerTaskNotFound("Task not found")
        if task.state != TaskState.MERGED:
            raise TrackerSyncConflict("Only merged tasks can be synchronized")
        return await sync_merged_task_to_linear(self._session, task)
