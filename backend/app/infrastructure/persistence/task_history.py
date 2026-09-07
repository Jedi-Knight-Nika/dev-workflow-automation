import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.job_enqueueing import EnqueuedJob
from app.application.ports.task_history import (
    ReviewFindingView,
    TaskEventView,
    TaskMetricsView,
    TaskRoleMetricsView,
    ValidationView,
)
from app.db.models import Job, ReviewFinding, TaskEvent, ValidationRecord, WorkerRun
from app.infrastructure.persistence.job_enqueueing import job_to_view


class SqlAlchemyTaskHistoryQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def jobs(self, task_id: uuid.UUID) -> list[EnqueuedJob]:
        records = (
            await self._session.scalars(
                select(Job).where(Job.task_id == task_id).order_by(Job.created_at)
            )
        ).all()
        return [job_to_view(record) for record in records]

    async def events(self, task_id: uuid.UUID) -> list[TaskEventView]:
        records = (
            await self._session.scalars(
                select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id)
            )
        ).all()
        return [
            TaskEventView(
                record.id,
                record.task_id,
                record.source,
                record.event_type,
                record.payload,
                record.created_at,
            )
            for record in records
        ]

    async def validations(self, task_id: uuid.UUID) -> list[ValidationView]:
        records = (
            await self._session.scalars(
                select(ValidationRecord)
                .where(ValidationRecord.task_id == task_id)
                .order_by(ValidationRecord.created_at.desc())
            )
        ).all()
        return [
            ValidationView(
                record.id,
                record.provider,
                record.kind,
                record.name,
                record.status,
                record.revision,
                record.details_url,
                record.created_at,
            )
            for record in records
        ]

    async def findings(self, task_id: uuid.UUID) -> list[ReviewFindingView]:
        records = (
            await self._session.scalars(
                select(ReviewFinding)
                .where(ReviewFinding.task_id == task_id)
                .order_by(ReviewFinding.created_at.desc())
            )
        ).all()
        return [
            ReviewFindingView(
                record.id,
                record.reviewer_job_id,
                record.workspace_fingerprint,
                record.finding_fingerprint,
                record.occurrence_count,
                record.severity,
                record.file_path,
                record.line,
                record.message,
                record.status,
                record.created_at,
                record.last_seen_at,
                record.resolved_at,
            )
            for record in records
        ]

    async def metrics(self, task_id: uuid.UUID) -> TaskMetricsView:
        runs = (
            await self._session.scalars(
                select(WorkerRun)
                .join(Job, Job.id == WorkerRun.job_id)
                .where(Job.task_id == task_id)
                .order_by(WorkerRun.created_at)
            )
        ).all()
        by_role: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
        known_input = 0
        known_output = 0
        missing = 0
        duration = 0
        priced: float | None = 0.0
        for run in runs:
            input_tokens = run.input_tokens
            output_tokens = run.output_tokens
            if input_tokens is None or output_tokens is None:
                missing += 1
            known_input += input_tokens or 0
            known_output += output_tokens or 0
            duration += run.duration_ms or 0
            if run.estimated_cost_usd is None:
                priced = None
            elif priced is not None:
                priced += float(run.estimated_cost_usd)
            key = (
                run.role.value if hasattr(run.role, "value") else str(run.role),
                run.provider,
                run.model,
            )
            bucket = by_role[key]
            bucket[0] += 1
            bucket[1] += input_tokens or 0
            bucket[2] += output_tokens or 0
            bucket[3] += run.duration_ms or 0
        roles = tuple(
            TaskRoleMetricsView(role, provider, model, *values)
            for (role, provider, model), values in by_role.items()
        )
        return TaskMetricsView(
            attempts=len(runs),
            input_tokens=known_input,
            output_tokens=known_output,
            missing_usage_attempts=missing,
            duration_ms=duration,
            estimated_cost_usd=priced if runs else None,
            roles=roles,
        )
