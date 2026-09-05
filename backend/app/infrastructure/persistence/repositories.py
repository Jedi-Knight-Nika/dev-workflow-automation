import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, JobRole, TaskEvent
from app.db.models import Task as TaskRecord
from app.db.models import TaskState as TaskRecordState
from app.domain.tasks import Task, TaskState


def task_to_domain(record: TaskRecord) -> Task:
    return Task(
        id=record.id,
        title=record.title,
        description=record.description,
        priority=record.priority,
        state=TaskState(record.state.value),
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
            state=TaskRecordState(task.state.value),
            repository_id=task.repository_id,
            current_revision=task.current_revision,
            branch_name=task.branch_name,
            workspace_path=task.workspace_path,
            pull_request_number=task.pull_request_number,
            pull_request_url=task.pull_request_url,
            manual_takeover=task.manual_takeover,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        self._session.add(record)
        await self._session.flush()


class SqlAlchemyJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue_intake(self, task: Task, payload: dict[str, Any]) -> uuid.UUID:
        job = Job(
            task_id=task.id,
            role=JobRole.INTAKE,
            action="INTERPRET_TASK",
            priority=task.priority,
            payload=payload,
        )
        self._session.add(job)
        await self._session.flush()
        await SqlAlchemyEventRepository(self._session).add(
            task.id,
            "JOB_QUEUED",
            {"job_id": str(job.id), "role": JobRole.INTAKE.value, "action": job.action},
            source="system",
        )
        return job.id


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
