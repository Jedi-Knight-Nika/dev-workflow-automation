"""Optional retention of derived file rows; milestones and source records are preserved."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.activity.infrastructure.models import ActivityEvent, ActivityFileChange
from app.activity.infrastructure.projector import PROJECTION_LOCK


async def expire_file_details(
    sessions: async_sessionmaker[AsyncSession], days: int, batch_size: int = 100
) -> int:
    if days <= 0:
        return 0
    async with sessions() as session, session.begin():
        if not await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": PROJECTION_LOCK}
        ):
            return 0
        events = list(
            await session.scalars(
                select(ActivityEvent)
                .where(
                    ActivityEvent.kind == "CODE_CHANGED",
                    ActivityEvent.file_status.is_distinct_from("EXPIRED"),
                    ActivityEvent.occurred_at < datetime.now(UTC) - timedelta(days=days),
                )
                .order_by(ActivityEvent.occurred_at, ActivityEvent.sequence)
                .limit(batch_size)
            )
        )
        if not events:
            return 0
        await session.execute(
            delete(ActivityFileChange).where(
                ActivityFileChange.event_sequence.in_([event.sequence for event in events])
            )
        )
        for event in events:
            event.file_status = "EXPIRED"
        await session.execute(
            update(ActivityEvent)
            .where(
                ActivityEvent.kind == "VALIDATION_PASSED",
                tuple_(ActivityEvent.task_id, ActivityEvent.payload["head_sha"].astext).in_(
                    [
                        (event.task_id, event.payload["head_sha"])
                        for event in events
                        if event.payload.get("head_sha")
                    ]
                ),
            )
            .values(file_status="EXPIRED", file_retry_at=None)
        )
        return len(events)
