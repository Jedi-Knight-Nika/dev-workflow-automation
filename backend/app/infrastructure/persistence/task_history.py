import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.job_enqueueing import EnqueuedJob
from app.application.ports.task_history import ReviewFindingView, TaskEventView, ValidationView
from app.db.models import Job, ReviewFinding, TaskEvent, ValidationRecord
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
