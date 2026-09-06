import types
import uuid
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.tester_completion import (
    TesterCompletionCommand,
    TesterCompletionContext,
)
from app.db.models import Job, JobRole, JobState, Task, TaskState
from app.infrastructure.linear_sync import sync_current_task_state_to_linear
from app.infrastructure.persistence.job_operations import enqueue_job, record_event
from app.infrastructure.persistence.workflow_routing import route_completed_job


class SqlAlchemyTesterCompletionUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
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
            raise RuntimeError("Tester completion unit of work is not active")
        return self._session

    async def begin(self, command: TesterCompletionCommand) -> TesterCompletionContext | None:
        session = self._active()
        job = await session.get(Job, command.job_id, with_for_update=True)
        if job is None or job.lease_token != command.lease_token or job.role != JobRole.TESTER:
            return None
        task = await session.get(Task, job.task_id, with_for_update=True)
        if task is None:
            raise RuntimeError(f"Task {job.task_id} disappeared while its job was running")
        job.state = JobState.SUCCEEDED
        job.result = command.result
        job.failure_reason = None
        job.finished_at = command.finished_at
        job.lease_expires_at = None
        return TesterCompletionContext(
            job.id,
            task.id,
            command.result.get("result"),
            command.result,
            task.manual_takeover,
        )

    async def finish_during_takeover(self, context: TesterCompletionContext) -> None:
        await record_event(
            self._active(),
            context.task_id,
            "JOB_FINISHED_DURING_TAKEOVER",
            {"job_id": str(context.job_id), "state": JobState.SUCCEEDED.value},
        )

    async def apply(self, context: TesterCompletionContext) -> None:
        session = self._active()
        task = await session.get(Task, context.task_id)
        if task is None:
            raise RuntimeError("Task disappeared during Tester completion")
        route = await route_completed_job(
            session, task, context.job_id, context.outcome, {"tester_result": context.result}
        )
        if route is None:
            if context.outcome == "TEST_PASS":
                await enqueue_job(
                    session, task, JobRole.REVIEWER, "REVIEW_IMPLEMENTATION", payload=context.result
                )
            elif context.outcome == "TEST_FAILED":
                await enqueue_job(
                    session, task, JobRole.EXECUTOR, "FIX_TEST_FAILURES", payload=context.result
                )
            else:
                task.state = TaskState.NEEDS_HUMAN
                await record_event(
                    session,
                    task.id,
                    "TESTER_NEEDS_HUMAN",
                    {"job_id": str(context.job_id), "result": context.outcome},
                )
        await record_event(
            session,
            task.id,
            "JOB_SUCCEEDED",
            {"job_id": str(context.job_id), "result": context.outcome},
        )

    async def commit(self) -> None:
        await self._active().commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        task = await self._active().get(Task, task_id)
        if task is not None:
            await sync_current_task_state_to_linear(self._active(), task)


class SqlAlchemyTesterCompletionUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyTesterCompletionUnitOfWork:
        return SqlAlchemyTesterCompletionUnitOfWork(self._session_factory)
