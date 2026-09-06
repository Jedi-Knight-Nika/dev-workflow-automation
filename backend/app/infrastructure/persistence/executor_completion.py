import types
import uuid
from typing import Self

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.executor_completion import (
    ExecutorCompletionCommand,
    ExecutorCompletionContext,
)
from app.db.models import Job, JobRole, JobState, Task, TaskState
from app.domain.jobs import CompletionDirective
from app.infrastructure.external_task_sync import sync_external_task_state
from app.infrastructure.persistence.job_operations import (
    enqueue_job,
    record_event,
    release_workspace_lease,
)
from app.infrastructure.persistence.workflow_routing import route_completed_job


class SqlAlchemyExecutorCompletionUnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_executor_jobs: int,
        max_thinker_jobs: int,
    ) -> None:
        self._session_factory = session_factory
        self._max_executor_jobs = max_executor_jobs
        self._max_thinker_jobs = max_thinker_jobs
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        if self._session is not None:
            if exc is not None:
                await self._session.rollback()
            await self._session.close()

    def _active(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Executor completion unit of work is not active")
        return self._session

    async def begin(self, command: ExecutorCompletionCommand) -> ExecutorCompletionContext | None:
        session = self._active()
        job = await session.get(Job, command.job_id, with_for_update=True)
        if job is None or job.lease_token != command.lease_token or job.role != JobRole.EXECUTOR:
            return None
        task = await session.get(Task, job.task_id, with_for_update=True)
        if task is None:
            raise RuntimeError(f"Task {job.task_id} disappeared while its job was running")
        job.state = JobState.SUCCEEDED
        job.result = command.result
        job.failure_reason = None
        job.finished_at = command.finished_at
        job.lease_expires_at = None
        await release_workspace_lease(session, job)
        data = command.result.get("data", {})
        return ExecutorCompletionContext(
            job.id,
            task.id,
            job.action,
            command.result.get("result"),
            data if isinstance(data, dict) else {},
            command.result,
            task.manual_takeover,
        )

    async def finish_during_takeover(self, context: ExecutorCompletionContext) -> None:
        await record_event(
            self._active(),
            context.task_id,
            "JOB_FINISHED_DURING_TAKEOVER",
            {"job_id": str(context.job_id), "state": JobState.SUCCEEDED.value},
        )

    async def apply(
        self, context: ExecutorCompletionContext, directive: CompletionDirective
    ) -> None:
        session = self._active()
        task = await session.get(Task, context.task_id)
        if task is None:
            raise RuntimeError("Task disappeared during Executor completion")
        route = await route_completed_job(
            session, task, context.job_id, context.outcome, {"executor_result": context.result}
        )
        if route is not None:
            await record_event(
                session,
                task.id,
                "JOB_SUCCEEDED",
                {"job_id": str(context.job_id), "result": context.outcome},
            )
            return
        if directive == CompletionDirective.EXECUTOR_REVIEW:
            task.state = TaskState.LOCAL_VALIDATION
            await enqueue_job(
                session, task, JobRole.REVIEWER, "REVIEW_CHANGES", payload=context.result
            )
        elif directive == CompletionDirective.EXECUTOR_REPAIR:
            await self._enqueue_repair(task, context)
        elif directive == CompletionDirective.EXECUTOR_REPLAN:
            await self._enqueue_replan(task, context)
        else:
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session,
                task.id,
                "EXECUTOR_NEEDS_HUMAN",
                {
                    "job_id": str(context.job_id),
                    "outcome": context.outcome,
                    "details": context.data,
                },
            )
        await record_event(
            session,
            task.id,
            "JOB_SUCCEEDED",
            {"job_id": str(context.job_id), "result": context.outcome},
        )

    async def _enqueue_repair(self, task: Task, context: ExecutorCompletionContext) -> None:
        session = self._active()
        total = await session.scalar(
            select(func.count(Job.id)).where(Job.task_id == task.id, Job.role == JobRole.EXECUTOR)
        )
        if (total or 0) >= self._max_executor_jobs:
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session, task.id, "REPAIR_LIMIT_REACHED", {"limit": self._max_executor_jobs}
            )
            return
        await enqueue_job(
            session, task, JobRole.EXECUTOR, "REPAIR_LOCAL_VALIDATION", payload=context.result
        )

    async def _enqueue_replan(self, task: Task, context: ExecutorCompletionContext) -> None:
        session = self._active()
        total = await session.scalar(
            select(func.count(Job.id)).where(Job.task_id == task.id, Job.role == JobRole.THINKER)
        )
        if (total or 0) >= self._max_thinker_jobs:
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session, task.id, "REPLAN_LIMIT_REACHED", {"limit": self._max_thinker_jobs}
            )
            return
        task.state = TaskState.PLANNING
        await enqueue_job(
            session,
            task,
            JobRole.THINKER,
            "REVISE_PLAN",
            payload={"executor_result": context.result},
        )
        await record_event(session, task.id, "REPLAN_QUEUED", {"attempt": (total or 0) + 1})

    async def commit(self) -> None:
        await self._active().commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        task = await self._active().get(Task, task_id)
        if task is not None:
            await sync_external_task_state(self._active(), task)


class SqlAlchemyExecutorCompletionUnitOfWorkFactory:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_executor_jobs: int,
        max_thinker_jobs: int,
    ) -> None:
        self._session_factory = session_factory
        self._max_executor_jobs = max_executor_jobs
        self._max_thinker_jobs = max_thinker_jobs

    def __call__(self) -> SqlAlchemyExecutorCompletionUnitOfWork:
        return SqlAlchemyExecutorCompletionUnitOfWork(
            self._session_factory, self._max_executor_jobs, self._max_thinker_jobs
        )
