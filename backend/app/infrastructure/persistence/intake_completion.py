import types
import uuid
from typing import Self

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.intake_completion import (
    IntakeCompletionCommand,
    IntakeCompletionContext,
)
from app.db.models import (
    Job,
    JobRole,
    JobState,
    Repository,
    Task,
    TaskRepositoryScope,
    TaskState,
    Team,
)
from app.domain.jobs import CompletionDirective
from app.infrastructure.linear_sync import sync_current_task_state_to_linear
from app.infrastructure.persistence.job_operations import (
    enqueue_job,
    record_event,
    release_workspace_lease,
)
from app.infrastructure.persistence.workflow_routing import route_completed_job


class SqlAlchemyIntakeCompletionUnitOfWork:
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
            raise RuntimeError("Intake completion unit of work is not active")
        return self._session

    async def begin(self, command: IntakeCompletionCommand) -> IntakeCompletionContext | None:
        session = self._active()
        job = await session.get(Job, command.job_id, with_for_update=True)
        if job is None or job.lease_token != command.lease_token or job.role != JobRole.INTAKE:
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
        return IntakeCompletionContext(
            job.id,
            task.id,
            job.action,
            job.payload,
            command.result.get("result"),
            data if isinstance(data, dict) else {},
            task.manual_takeover,
        )

    async def finish_during_takeover(self, context: IntakeCompletionContext) -> None:
        await record_event(
            self._active(),
            context.task_id,
            "JOB_FINISHED_DURING_TAKEOVER",
            {"job_id": str(context.job_id), "state": JobState.SUCCEEDED.value},
        )

    async def apply(self, context: IntakeCompletionContext, directive: CompletionDirective) -> None:
        session = self._active()
        task = await session.get(Task, context.task_id)
        if task is None:
            raise RuntimeError("Task disappeared during Intake completion")
        await self._apply_repository_scope(task, context.data)
        route = await route_completed_job(
            session, task, context.job_id, context.outcome, {"intake": context.data}
        )
        if route is not None:
            await record_event(
                session,
                task.id,
                "JOB_SUCCEEDED",
                {"job_id": str(context.job_id), "result": context.outcome},
            )
            return
        if directive == CompletionDirective.INTAKE_NEEDS_HUMAN:
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session,
                task.id,
                "INTAKE_NEEDS_HUMAN",
                {"job_id": str(context.job_id), "interpretation": context.data},
            )
        else:
            await record_event(
                session,
                task.id,
                "INTAKE_INTERPRETED",
                {"job_id": str(context.job_id), "interpretation": context.data},
            )
            if directive == CompletionDirective.INTAKE_INFORMATIONAL:
                previous_state = context.job_payload.get("previous_state")
                task.state = (
                    TaskState(previous_state)
                    if isinstance(previous_state, str)
                    else TaskState.WAITING_GITHUB
                )
            elif directive == CompletionDirective.INTAKE_REPAIR:
                await self._enqueue_repair(task, context)
            elif directive == CompletionDirective.INTAKE_REPLAN:
                await self._enqueue_replan(task, context)
            else:
                await enqueue_job(
                    session,
                    task,
                    JobRole.THINKER,
                    "CREATE_PLAN",
                    payload={"intake": context.data},
                )
        await record_event(
            session,
            task.id,
            "JOB_SUCCEEDED",
            {"job_id": str(context.job_id), "result": context.outcome},
        )

    async def _apply_repository_scope(self, task: Task, data: dict[str, object]) -> None:
        if task.team_id is None:
            return
        session = self._active()
        team = await session.get(Team, task.team_id)
        if team is None:
            return
        statement = select(Repository).where(
            Repository.enabled.is_(True), Repository.archived_at.is_(None)
        )
        if team.repository_ids:
            statement = statement.where(
                Repository.id.in_([uuid.UUID(value) for value in team.repository_ids])
            )
        candidates = list((await session.scalars(statement)).all())
        candidates_by_id = {repository.id: repository for repository in candidates}
        raw_ids = data.get("repository_ids")
        selected_ids: list[uuid.UUID] = []
        if isinstance(raw_ids, list):
            for value in raw_ids:
                try:
                    repository_id = uuid.UUID(str(value))
                except ValueError as exc:
                    raise ValueError(f"Intake selected invalid repository ID: {value}") from exc
                if repository_id not in candidates_by_id:
                    raise ValueError("Intake selected a repository outside the Team scope")
                if repository_id not in selected_ids:
                    selected_ids.append(repository_id)
        if not selected_ids and len(candidates) == 1:
            selected_ids = [candidates[0].id]
        if not selected_ids:
            return

        reason = str(data.get("repository_selection_reason") or "Selected during Intake")
        confidence_value = data.get("confidence")
        confidence = float(confidence_value) if isinstance(confidence_value, (int, float)) else None
        existing_scopes = list(
            (
                await session.scalars(
                    select(TaskRepositoryScope).where(TaskRepositoryScope.task_id == task.id)
                )
            ).all()
        )
        existing_by_repository = {scope.repository_id: scope for scope in existing_scopes}
        for index, repository_id in enumerate(selected_ids):
            scope = existing_by_repository.get(repository_id)
            if scope is None:
                scope = TaskRepositoryScope(
                    task_id=task.id,
                    repository_id=repository_id,
                    selected_by="INTAKE",
                )
                session.add(scope)
            scope.reason = reason
            scope.confidence = confidence
            scope.is_primary = index == 0
        selected_set = set(selected_ids)
        for scope in existing_scopes:
            if scope.repository_id in selected_set:
                continue
            if scope.workspace_path or scope.changed or scope.pull_request_number:
                scope.is_primary = False
                continue
            await session.delete(scope)
        # Preserve compatibility while execution/delivery consumers migrate to scopes.
        task.repository_id = selected_ids[0]
        await record_event(
            session,
            task.id,
            "TASK_REPOSITORY_SCOPE_SELECTED",
            {
                "repository_ids": [str(repository_id) for repository_id in selected_ids],
                "reason": reason,
                "confidence": confidence,
            },
        )

    async def _enqueue_repair(self, task: Task, context: IntakeCompletionContext) -> None:
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
            session,
            task,
            JobRole.EXECUTOR,
            "REPAIR_EXTERNAL_FEEDBACK",
            payload={"intake": context.data, "external_comment": context.job_payload},
        )

    async def _enqueue_replan(self, task: Task, context: IntakeCompletionContext) -> None:
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
            payload={
                "executor_result": {
                    "intake": context.data,
                    "external_comment": context.job_payload,
                }
            },
        )
        await record_event(session, task.id, "REPLAN_QUEUED", {"attempt": (total or 0) + 1})

    async def commit(self) -> None:
        await self._active().commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        task = await self._active().get(Task, task_id)
        if task is not None:
            await sync_current_task_state_to_linear(self._active(), task)


class SqlAlchemyIntakeCompletionUnitOfWorkFactory:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_executor_jobs: int,
        max_thinker_jobs: int,
    ) -> None:
        self._session_factory = session_factory
        self._max_executor_jobs = max_executor_jobs
        self._max_thinker_jobs = max_thinker_jobs

    def __call__(self) -> SqlAlchemyIntakeCompletionUnitOfWork:
        return SqlAlchemyIntakeCompletionUnitOfWork(
            self._session_factory, self._max_executor_jobs, self._max_thinker_jobs
        )
