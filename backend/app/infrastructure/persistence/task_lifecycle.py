import types
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.task_lifecycle import (
    TaskLifecycleContext,
    WorkspaceRefreshUnavailable,
)
from app.db.models import Job, JobState, TaskAssignment
from app.db.models import Task as TaskRecord
from app.db.models import TaskState as TaskRecordState
from app.domain.tasks import LifecycleDirective, Task, TaskState
from app.infrastructure.external_task_sync import sync_external_task_state
from app.infrastructure.git.workspaces import GitCommandError, run_git
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.persistence.repositories import task_to_domain
from app.infrastructure.workers.executor import workspace_fingerprint


class SqlAlchemyTaskLifecycleUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._task: TaskRecord | None = None

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
            raise RuntimeError("Task lifecycle unit of work is not active")
        return self._session

    async def load(self, task_id: uuid.UUID) -> TaskLifecycleContext | None:
        self._task = await self._active().get(TaskRecord, task_id, with_for_update=True)
        if self._task is None:
            return None
        return TaskLifecycleContext(
            self._task.id,
            TaskState(self._task.state.value),
            self._task.manual_takeover,
            self._task.pull_request_number is not None,
            bool(self._task.workspace_path),
        )

    async def refresh_workspace(self, task_id: uuid.UUID) -> tuple[str, str]:
        if self._task is None or self._task.id != task_id or not self._task.workspace_path:
            raise RuntimeError("Task workspace is unavailable")
        workspace = Path(self._task.workspace_path)
        try:
            return await run_git("rev-parse", "HEAD", cwd=workspace), await workspace_fingerprint(
                workspace
            )
        except GitCommandError as exc:
            raise WorkspaceRefreshUnavailable(f"Workspace refresh failed: {exc}") from exc

    async def apply(
        self,
        context: TaskLifecycleContext,
        directive: LifecycleDirective,
        *,
        revision: str | None,
        workspace_fingerprint: str | None,
    ) -> Task:
        if self._task is None or self._task.id != context.task_id:
            raise RuntimeError("Task lifecycle context is not loaded")
        session = self._active()
        self._task.state = TaskRecordState(directive.state.value)
        self._task.manual_takeover = directive.manual_takeover
        if directive.archive:
            self._task.archived_at = datetime.now(UTC)
        if revision is not None:
            self._task.current_revision = revision
        cancelled_jobs = 0
        if directive.cancel_queued_jobs:
            queued = list(
                (
                    await session.scalars(
                        select(Job).where(
                            Job.task_id == self._task.id,
                            Job.state.in_(
                                [
                                    JobState.QUEUED,
                                    JobState.RETRY_WAIT,
                                    JobState.WAITING_PROVIDER,
                                    JobState.WAITING_INTEGRATION,
                                    JobState.WAITING_CONFIGURATION,
                                    JobState.WAITING_HUMAN,
                                ]
                            ),
                        )
                    )
                ).all()
            )
            for job in queued:
                job.state = JobState.CANCELLED
            cancelled_jobs = len(queued)
        if directive.state == TaskState.NEW:
            assignment = await session.scalar(
                select(TaskAssignment).where(TaskAssignment.task_id == self._task.id)
            )
            if assignment is not None:
                assignment.status = "QUEUED"
                assignment.started_at = None
        payload: dict[str, Any]
        if directive.archive:
            event_type, payload = "TASK_ARCHIVED", {}
        elif directive.state == TaskState.CANCELLED:
            event_type, payload = "TASK_CANCELLED", {"cancelled_jobs": cancelled_jobs}
        elif directive.state == TaskState.NEW and context.state != TaskState.NEW:
            event_type, payload = "TASK_REOPENED", {"cancelled_jobs": cancelled_jobs}
        elif directive.manual_takeover:
            event_type, payload = (
                "MANUAL_TAKEOVER_STARTED",
                {
                    "cancelled_queued_jobs": cancelled_jobs,
                    "workspace_path": self._task.workspace_path,
                },
            )
        elif context.manual_takeover:
            event_type, payload = (
                "MANUAL_TAKEOVER_ENDED",
                {
                    "revision": self._task.current_revision,
                    "workspace_fingerprint": workspace_fingerprint,
                },
            )
        else:
            event_type, payload = "TASK_PAUSED", {}
        await record_event(session, self._task.id, event_type, payload, source="user")
        await session.flush()
        return task_to_domain(self._task)

    async def commit(self) -> None:
        await self._active().commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        task = await self._active().get(TaskRecord, task_id)
        if task is not None:
            await sync_external_task_state(self._active(), task)


class SqlAlchemyTaskLifecycleUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyTaskLifecycleUnitOfWork:
        return SqlAlchemyTaskLifecycleUnitOfWork(self._session_factory)
