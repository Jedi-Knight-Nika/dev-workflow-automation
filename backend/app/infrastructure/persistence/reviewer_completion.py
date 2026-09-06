import types
import uuid
from typing import Self

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.reviewer_completion import (
    ReviewerCompletionCommand,
    ReviewerCompletionContext,
)
from app.db.models import (
    Job,
    JobRole,
    JobState,
    Repository,
    Task,
    TaskState,
    ValidationRecord,
    WorkflowNode,
)
from app.domain.jobs import CompletionDirective
from app.infrastructure.linear_sync import sync_current_task_state_to_linear
from app.infrastructure.persistence.job_operations import (
    enqueue_job,
    record_event,
    release_workspace_lease,
)
from app.infrastructure.persistence.reviews import persist_review_result
from app.infrastructure.persistence.workflow_routing import route_completed_job
from app.infrastructure.pull_requests.operations import publish_pull_request

log = structlog.get_logger()


class SqlAlchemyReviewerCompletionUnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_executor_jobs: int,
        max_thinker_jobs: int,
        max_same_finding_repeats: int,
    ) -> None:
        self._session_factory = session_factory
        self._max_executor_jobs = max_executor_jobs
        self._max_thinker_jobs = max_thinker_jobs
        self._max_same_finding_repeats = max_same_finding_repeats
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
            raise RuntimeError("Reviewer completion unit of work is not active")
        return self._session

    async def begin(self, command: ReviewerCompletionCommand) -> ReviewerCompletionContext | None:
        session = self._active()
        job = await session.get(Job, command.job_id, with_for_update=True)
        if job is None or job.lease_token != command.lease_token or job.role != JobRole.REVIEWER:
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
        repeat_count = (
            0 if task.manual_takeover else await persist_review_result(session, job, command.result)
        )
        data = command.result.get("data", {})
        return ReviewerCompletionContext(
            job.id,
            task.id,
            job.action,
            command.result.get("result"),
            data if isinstance(data, dict) else {},
            command.result,
            repeat_count,
            task.manual_takeover,
        )

    async def finish_during_takeover(self, context: ReviewerCompletionContext) -> None:
        await record_event(
            self._active(),
            context.task_id,
            "JOB_FINISHED_DURING_TAKEOVER",
            {"job_id": str(context.job_id), "state": JobState.SUCCEEDED.value},
        )

    async def apply(
        self, context: ReviewerCompletionContext, directive: CompletionDirective
    ) -> bool:
        session = self._active()
        task = await session.get(Task, context.task_id)
        if task is None:
            raise RuntimeError("Task disappeared during Reviewer completion")
        data = context.result.get("data", {})
        if context.outcome == "PASS" and isinstance(data, dict) and data.get("content_revision"):
            session.add(
                ValidationRecord(
                    task_id=task.id,
                    provider="internal",
                    kind="REVIEWER",
                    name="semantic-review",
                    status="PASSED",
                    revision=str(data["content_revision"]),
                    payload={
                        "repository_sha": data.get("repository_sha"),
                        "configuration_hash": data.get("validation_configuration_hash"),
                    },
                )
            )
        if directive in {
            CompletionDirective.REVIEW_REPAIR,
            CompletionDirective.REVIEW_REPLAN,
        } and await self._review_cycle_limit_reached(task, context):
            await record_event(
                session,
                task.id,
                "JOB_SUCCEEDED",
                {"job_id": str(context.job_id), "result": context.outcome},
            )
            return False
        route = await route_completed_job(
            session, task, context.job_id, context.outcome, {"reviewer_result": context.result}
        )
        if route is not None:
            await record_event(
                session,
                task.id,
                "JOB_SUCCEEDED",
                {"job_id": str(context.job_id), "result": context.outcome},
            )
            return route.publish
        should_publish = False
        if directive == CompletionDirective.REVIEW_PUBLISH:
            task.state = TaskState.WAITING_GITHUB
            should_publish = bool(task.repository_id and task.workspace_path)
        elif directive == CompletionDirective.REVIEW_NEEDS_HUMAN:
            task.state = TaskState.NEEDS_HUMAN
            event_type = (
                "REPEATED_FINDING_LIMIT_REACHED"
                if context.repeat_count >= self._max_same_finding_repeats
                else "REVIEW_NEEDS_HUMAN"
            )
            details = (
                {
                    "job_id": str(context.job_id),
                    "occurrences": context.repeat_count,
                    "limit": self._max_same_finding_repeats,
                }
                if event_type == "REPEATED_FINDING_LIMIT_REACHED"
                else {
                    "job_id": str(context.job_id),
                    "outcome": context.outcome,
                    "details": context.data,
                }
            )
            await record_event(session, task.id, event_type, details)
        elif directive == CompletionDirective.REVIEW_REPAIR:
            await self._enqueue_repair(task, context)
        elif directive == CompletionDirective.REVIEW_REPLAN:
            await self._enqueue_replan(task, context)
        await record_event(
            session,
            task.id,
            "JOB_SUCCEEDED",
            {"job_id": str(context.job_id), "result": context.outcome},
        )
        return should_publish

    async def _review_cycle_limit_reached(
        self, task: Task, context: ReviewerCompletionContext
    ) -> bool:
        """Apply the configured workflow-node circuit breaker before another repair loop."""
        session = self._active()
        job = await session.get(Job, context.job_id)
        node = (
            await session.get(WorkflowNode, job.workflow_node_id)
            if job is not None and job.workflow_node_id is not None
            else None
        )
        if node is None:
            return False
        completed_cycles = await session.scalar(
            select(func.count(Job.id)).where(
                Job.task_id == task.id,
                Job.workflow_node_id == node.id,
                Job.role == JobRole.REVIEWER,
                Job.state == JobState.SUCCEEDED,
                Job.result.is_not(None),
            )
        )
        strategy_limit = int(
            (task.execution_strategy or {}).get("max_review_cycles", node.max_review_cycles)
        )
        effective_limit = min(node.max_review_cycles, strategy_limit)
        if (completed_cycles or 0) < effective_limit:
            return False
        task.state = TaskState.NEEDS_HUMAN
        await record_event(
            session,
            task.id,
            "REVIEW_CYCLE_LIMIT_REACHED",
            {
                "job_id": str(context.job_id),
                "workflow_node_id": str(node.id),
                "cycles": completed_cycles or 0,
                "limit": effective_limit,
            },
        )
        return True

    async def _enqueue_repair(self, task: Task, context: ReviewerCompletionContext) -> None:
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
            session, task, JobRole.EXECUTOR, "REPAIR_INTERNAL_REVIEW", payload=context.result
        )

    async def _enqueue_replan(self, task: Task, context: ReviewerCompletionContext) -> None:
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

    async def publish(self, task_id: uuid.UUID) -> None:
        session = self._active()
        try:
            task = await session.get(Task, task_id, with_for_update=True)
            if (
                task is None
                or task.state != TaskState.WAITING_GITHUB
                or task.manual_takeover
                or task.repository_id is None
            ):
                return
            repository = await session.get(Repository, task.repository_id)
            if repository is None or not repository.enabled:
                raise RuntimeError("Reviewed task repository is unavailable")
            await publish_pull_request(session, task, repository)
        except Exception as exc:
            log.exception("automatic_pull_request_publish_failed", task_id=str(task_id))
            await session.rollback()
            task = await session.get(Task, task_id, with_for_update=True)
            if task is None:
                return
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session, task.id, "AUTOMATIC_PR_PUBLISH_FAILED", {"error": str(exc)[:1000]}
            )
            await session.commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        task = await self._active().get(Task, task_id)
        if task is not None:
            await sync_current_task_state_to_linear(self._active(), task)


class SqlAlchemyReviewerCompletionUnitOfWorkFactory:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_executor_jobs: int,
        max_thinker_jobs: int,
        max_same_finding_repeats: int,
    ) -> None:
        self._session_factory = session_factory
        self._max_executor_jobs = max_executor_jobs
        self._max_thinker_jobs = max_thinker_jobs
        self._max_same_finding_repeats = max_same_finding_repeats

    def __call__(self) -> SqlAlchemyReviewerCompletionUnitOfWork:
        return SqlAlchemyReviewerCompletionUnitOfWork(
            self._session_factory,
            self._max_executor_jobs,
            self._max_thinker_jobs,
            self._max_same_finding_repeats,
        )
