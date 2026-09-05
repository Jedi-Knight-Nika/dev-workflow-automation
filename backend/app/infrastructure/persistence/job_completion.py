import types
import uuid
from datetime import timedelta
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.job_completion import FailedJobCommand, FailedJobContext
from app.db.models import Job, JobState, Task, TaskState
from app.infrastructure.linear_sync import sync_current_task_state_to_linear
from app.infrastructure.persistence.job_operations import record_event, release_workspace_lease


class SqlAlchemyFailedCompletionUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._command: FailedJobCommand | None = None

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

    def _active_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Failed-completion unit of work is not active")
        return self._session

    async def begin(self, command: FailedJobCommand) -> FailedJobContext | None:
        session = self._active_session()
        job = await session.get(Job, command.job_id, with_for_update=True)
        if job is None or job.lease_token != command.lease_token:
            return None
        task = await session.get(Task, job.task_id, with_for_update=True)
        if task is None:
            raise RuntimeError(f"Task {job.task_id} disappeared while its job was running")
        job.state = JobState(command.terminal_state)
        job.result = None
        job.failure_reason = command.failure
        job.finished_at = command.finished_at
        job.lease_expires_at = None
        await release_workspace_lease(session, job)
        self._command = command
        return FailedJobContext(job.id, task.id, job.attempt, task.manual_takeover)

    async def schedule_retry(
        self, context: FailedJobContext, delay_seconds: int, max_attempts: int
    ) -> None:
        session = self._active_session()
        job = await session.get(Job, context.job_id)
        if job is None or self._command is None:
            raise RuntimeError("Failed job disappeared before retry scheduling")
        job.state = JobState.RETRY_WAIT
        job.worker_id = None
        job.lease_token = None
        job.retry_not_before = self._command.finished_at + timedelta(seconds=delay_seconds)
        await record_event(
            session,
            context.task_id,
            "JOB_RETRY_SCHEDULED",
            {
                "job_id": str(context.job_id),
                "attempt": context.attempt,
                "max_attempts": max_attempts,
                "delay_seconds": delay_seconds,
                "reason": self._command.failure,
            },
        )

    async def exhaust(self, context: FailedJobContext) -> None:
        session = self._active_session()
        task = await session.get(Task, context.task_id)
        if task is None or self._command is None:
            raise RuntimeError("Task disappeared before failure escalation")
        task.state = TaskState.NEEDS_HUMAN
        await record_event(
            session,
            context.task_id,
            "JOB_FAILED",
            {
                "job_id": str(context.job_id),
                "attempts": context.attempt,
                "reason": self._command.failure,
            },
        )

    async def finish_during_takeover(self, context: FailedJobContext) -> None:
        if self._command is None:
            raise RuntimeError("Failure command is unavailable")
        await record_event(
            self._active_session(),
            context.task_id,
            "JOB_FINISHED_DURING_TAKEOVER",
            {"job_id": str(context.job_id), "state": self._command.terminal_state},
        )

    async def commit(self) -> None:
        await self._active_session().commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        session = self._active_session()
        task = await session.get(Task, task_id)
        if task is not None:
            await sync_current_task_state_to_linear(session, task)


class SqlAlchemyFailedCompletionUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyFailedCompletionUnitOfWork:
        return SqlAlchemyFailedCompletionUnitOfWork(self._session_factory)
