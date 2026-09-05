from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.job_enqueueing import (
    EnqueuedJob,
    EnqueueJobCommand,
    EnqueueTaskConflict,
    EnqueueTaskNotFound,
)
from app.db.models import Job, JobRole, Task, TaskState
from app.infrastructure.persistence.job_operations import enqueue_job


def job_to_view(job: Job) -> EnqueuedJob:
    return EnqueuedJob(
        id=job.id,
        task_id=job.task_id,
        role=job.role.value,
        action=job.action,
        priority=job.priority,
        state=job.state.value,
        attempt=job.attempt,
        payload=job.payload,
        result=job.result,
        worker_id=job.worker_id,
        failure_reason=job.failure_reason,
        retry_not_before=job.retry_not_before,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


class SqlAlchemyJobEnqueueWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, command: EnqueueJobCommand) -> EnqueuedJob:
        task = await self._session.get(Task, command.task_id, with_for_update=True)
        if task is None:
            raise EnqueueTaskNotFound("Task not found")
        if task.state in {TaskState.CANCELLED, TaskState.PAUSED}:
            raise EnqueueTaskConflict(f"Cannot enqueue work for {task.state.value} task")
        job = await enqueue_job(
            self._session,
            task,
            JobRole(command.role),
            command.action,
            command.priority,
            command.payload,
        )
        await self._session.commit()
        await self._session.refresh(job)
        return job_to_view(job)
