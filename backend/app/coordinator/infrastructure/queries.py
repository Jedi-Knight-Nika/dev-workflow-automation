"""Reusable Coordinator queries; transaction and lock ownership stay with callers."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.coordinator.infrastructure.models import CoordinatorEvent, HumanRequest
from app.engineering.infrastructure.task_models import Task


def latest_human_request(task: Task) -> Select[tuple[HumanRequest]]:
    return (
        select(HumanRequest)
        .where(
            HumanRequest.task_id == task.id,
            HumanRequest.status.in_(["OPEN", "ANSWERED"]),
            HumanRequest.requirement_revision == task.requirement_version,
            HumanRequest.lifecycle_revision == task.lifecycle_version,
        )
        .order_by(HumanRequest.created_at.desc())
        .limit(1)
    )


async def requeue_run_events(session: AsyncSession, run_id: UUID) -> None:
    """Retain the entire event batch for a fresh decision, without replaying effects."""
    await session.execute(
        update(CoordinatorEvent)
        .where(CoordinatorEvent.run_id == run_id)
        .values(status="QUEUED", run_id=None, available_at=datetime.now(UTC))
    )
