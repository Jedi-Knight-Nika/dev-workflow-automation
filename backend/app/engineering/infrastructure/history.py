import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.application.ports.job_enqueueing import EnqueuedJob
from app.engineering.application.ports.task_history import (
    NativeRunView,
    TaskEventView,
    TaskMetricsView,
    ValidationView,
)
from app.engineering.application.task_usage import UsageSample, task_usage
from app.engineering.infrastructure.job_views import job_to_view
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Job, TaskEvent


class SqlAlchemyTaskHistoryQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def runs(self, task_id: uuid.UUID) -> list[NativeRunView]:
        rows = await self._session.scalars(
            select(AIRun)
            .where(AIRun.task_id == task_id)
            .order_by(AIRun.started_at.desc())
            .limit(200)
        )
        return [
            NativeRunView(
                row.id,
                row.role_kind,
                row.provider,
                row.model,
                row.harness,
                row.status,
                row.input_tokens,
                row.output_tokens,
                row.cache_read_tokens,
                str(row.provider_cost_usd)
                if row.provider_cost_usd is not None
                else str(row.calculated_cost_usd)
                if row.calculated_cost_usd is not None
                else None,
                row.usage_complete,
                row.artifact,
                row.failure_code,
                row.started_at,
                row.finished_at,
                row.requirement_version,
            )
            for row in rows
        ]

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
                select(ValidationRun)
                .where(ValidationRun.task_id == task_id)
                .order_by(ValidationRun.started_at.desc())
            )
        ).all()
        return [
            ValidationView(
                record.id,
                "local",
                "deterministic",
                " ".join(record.command),
                record.status,
                record.head_sha,
                None,
                record.started_at,
                record.exit_code,
                record.output_tail,
                record.finished_at,
            )
            for record in records
        ]

    async def metrics(self, task_id: uuid.UUID) -> TaskMetricsView:
        native_runs = (
            await self._session.scalars(select(AIRun).where(AIRun.task_id == task_id))
        ).all()
        samples = [
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
        ]
        return task_usage(samples)
