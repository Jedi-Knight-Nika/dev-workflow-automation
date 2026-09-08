import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.job_enqueueing import EnqueuedJob
from app.application.ports.task_history import (
    ReviewFindingView,
    TaskEventView,
    TaskMetricsView,
    ValidationView,
)
from app.application.task_usage import UsageSample, task_usage
from app.db.models import AIRun, Job, ReviewFinding, TaskEvent, ValidationRecord, WorkerRun
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
        native_runs = (
            await self._session.scalars(select(AIRun).where(AIRun.task_id == task_id))
        ).all()
        samples = [
            UsageSample(
                run.role.value,
                run.provider,
                run.model,
                run.input_tokens,
                run.output_tokens,
                run.duration_ms,
                Decimal(str(run.estimated_cost_usd))
                if run.estimated_cost_usd is not None
                else None,
            )
            for run in runs
        ]
        samples.extend(
            UsageSample(
                run.role_kind,
                run.provider,
                run.model,
                run.input_tokens,
                run.output_tokens,
                run.provider_duration_ms,
                run.provider_cost_usd
                if run.provider_cost_usd is not None
                else run.calculated_cost_usd,
                native=True,
                complete=run.usage_complete,
            )
            for run in native_runs
        )
        return task_usage(samples)
