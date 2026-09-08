import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.domain.lifecycle import Stage, TaskStatus, WaitReason
from app.engineering.domain.task import Task
from app.engineering.infrastructure.task_models import Task as TaskRecord
from app.engineering.infrastructure.task_models import TaskEvent


def task_to_domain(record: TaskRecord) -> Task:
    return Task(
        id=record.id,
        title=record.title,
        description=record.description,
        priority=record.priority,
        status=TaskStatus(record.status),
        stage=Stage(record.stage),
        wait_reason=WaitReason(record.wait_reason),
        lifecycle_version=record.lifecycle_version,
        requirement_version=record.requirement_version,
        external_key=record.external_key,
        repository_id=record.repository_id,
        current_revision=record.current_revision,
        branch_name=record.branch_name,
        workspace_path=record.workspace_path,
        pull_request_number=record.pull_request_number,
        pull_request_url=record.pull_request_url,
        manual_takeover=record.manual_takeover,
        created_at=record.created_at,
        updated_at=record.updated_at,
        project_name=record.project_name,
        labels=tuple(record.labels or []),
        estimate=float(record.estimate) if record.estimate is not None else None,
        due_at=record.due_at,
    )


class SqlAlchemyTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: Task) -> None:
        record = TaskRecord(
            id=task.id,
            external_key=task.external_key,
            title=task.title,
            description=task.description,
            priority=task.priority,
            status=task.status.value,
            stage=task.stage.value,
            wait_reason=task.wait_reason.value,
            repository_id=task.repository_id,
            current_revision=task.current_revision,
            branch_name=task.branch_name,
            workspace_path=task.workspace_path,
            pull_request_number=task.pull_request_number,
            pull_request_url=task.pull_request_url,
            manual_takeover=task.manual_takeover,
            created_at=task.created_at,
            updated_at=task.updated_at,
            project_name=task.project_name,
            labels=list(task.labels),
            estimate=task.estimate,
            due_at=task.due_at,
        )
        self._session.add(record)
        await self._session.flush()


class SqlAlchemyJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue_intake(self, task: Task, payload: dict[str, Any]) -> uuid.UUID:
        from app.engineering.infrastructure.job_queue import request_execution
        from app.teams.infrastructure.routing import assign_routed_team

        record = await self._session.get(TaskRecord, task.id)
        if record is None:
            raise LookupError("Task not found")
        await assign_routed_team(self._session, record, reason="manual-creation")
        await request_execution(self._session, record, actor="user:manual-creation")
        task.status = TaskStatus(record.status)
        task.stage = Stage(record.stage)
        task.wait_reason = WaitReason(record.wait_reason)
        task.lifecycle_version = record.lifecycle_version
        task.requirement_version = record.requirement_version
        task.workspace_path = record.workspace_path
        task.branch_name = record.branch_name
        return task.id


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        task_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
        *,
        source: str,
    ) -> None:
        self._session.add(
            TaskEvent(task_id=task_id, event_type=event_type, payload=payload, source=source)
        )
