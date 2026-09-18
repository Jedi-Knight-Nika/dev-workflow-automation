from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.domain.lifecycle import Stage, TaskStatus, WaitReason
from app.engineering.domain.task import Task
from app.engineering.infrastructure.job_queue import request_execution
from app.engineering.infrastructure.task_models import Task as TaskRecord
from app.teams.infrastructure.routing import assign_routed_team


class SqlTaskExecution:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, task: Task) -> None:
        record = await self._session.get(TaskRecord, task.id)
        if record is None:
            raise LookupError("Task not found")
        if record.team_id is None:
            await assign_routed_team(self._session, record, reason="manual-creation")
        await request_execution(self._session, record, actor="user:manual-creation")
        task.status = TaskStatus(record.status)
        task.stage = Stage(record.stage)
        task.wait_reason = WaitReason(record.wait_reason)
        task.lifecycle_version = record.lifecycle_version
        task.requirement_version = record.requirement_version
        task.workspace_path = record.workspace_path
        task.branch_name = record.branch_name
        task.team_id = record.team_id
