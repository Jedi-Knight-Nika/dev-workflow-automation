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
from app.db.models import Job, JobRole, JobState, TaskAssignment
from app.db.models import Task as TaskRecord
from app.db.models import TaskState as TaskRecordState
from app.domain.tasks import LifecycleDirective, Task, TaskState
from app.engineering.domain.lifecycle import Action, InvalidTransition
from app.engineering.infrastructure.controls import control_task
from app.infrastructure.external_task_sync import sync_external_task_state
from app.infrastructure.git.workspaces import GitCommandError, run_git
from app.infrastructure.persistence.job_operations import enqueue_job, record_event
from app.infrastructure.persistence.repositories import task_to_domain
from app.infrastructure.pull_requests.feedback import latest_github_pull_request_feedback
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
        if self._task.execution_version == 2:
            # Untrusted repository commands stay in the isolated validation container.
            return self._task.current_revision or "", str(self._task.progress_fingerprint or {})
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
        if self._task.execution_version == 2:
            action = (
                Action.TAKEOVER
                if directive.manual_takeover
                else Action.RELEASE_TAKEOVER
                if context.manual_takeover
                else Action.CANCEL
                if directive.state == TaskState.CANCELLED
                else Action.PAUSE
                if directive.state == TaskState.PAUSED or directive.archive
                else Action.RESUME
            )
            try:
                await control_task(session, self._task, action, actor="user:ticket-control")
            except InvalidTransition as exc:
                from app.domain.tasks import InvalidTaskTransition

                raise InvalidTaskTransition(str(exc)) from exc
            if directive.archive:
                self._task.archived_at = datetime.now(UTC)
            return task_to_domain(self._task)
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

    async def enqueue_reopened_task(self, context: TaskLifecycleContext) -> None:
        session = self._active()
        task = await session.get(TaskRecord, context.task_id)
        if task is not None and task.execution_version == 2:
            return  # Phase job was queued atomically with the V2 transition.
        if task is None or task.team_id is None or task.state != TaskRecordState.NEW:
            return
        active_job = await session.scalar(
            select(Job.id).where(
                Job.task_id == task.id,
                Job.state.in_([JobState.QUEUED, JobState.CLAIMED, JobState.RUNNING]),
            )
        )
        if active_job is not None:
            return
        job_payload = None
        if context.has_pull_request:
            job_payload = await latest_github_pull_request_feedback(session, task)
            if job_payload is None:
                previous = await session.scalar(
                    select(Job)
                    .where(
                        Job.task_id == task.id,
                        Job.role == JobRole.DELIVERER,
                        Job.action == "INTERPRET_EXTERNAL_COMMENT",
                    )
                    .order_by(Job.created_at.desc())
                    .limit(1)
                )
                if previous is not None:
                    job_payload = {
                        **previous.payload,
                        "previous_state": TaskState.NEW.value,
                        "replayed_after_manual_reopen": True,
                    }
        await enqueue_job(
            session,
            task,
            JobRole.DELIVERER,
            "INTERPRET_EXTERNAL_COMMENT" if job_payload else "INTERPRET_TASK",
            payload=job_payload or {"reason": "manual_status_change"},
        )
        await session.commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        task = await self._active().get(TaskRecord, task_id)
        if task is not None:
            await sync_external_task_state(self._active(), task)


class SqlAlchemyTaskLifecycleUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyTaskLifecycleUnitOfWork:
        return SqlAlchemyTaskLifecycleUnitOfWork(self._session_factory)
