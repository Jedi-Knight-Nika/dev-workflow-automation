"""Transactional notification storage; no network calls while holding database locks."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.configuration.settings import get_settings
from app.platform.messaging.application.ports import OutboxClaim, TaskWakeup
from app.platform.persistence.base import Base, utcnow


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (Index("ix_notification_due", "published_at", "available_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID]
    revision: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(100))


def enqueue_task_wakeup(session: AsyncSession, task_id: UUID, revision: int) -> None:
    if get_settings().event_transport == "rabbitmq":
        session.add(NotificationOutbox(task_id=task_id, revision=revision))


class SqlEventOutbox:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], *, lease_seconds: float = 60
    ) -> None:
        self.sessions, self.lease_seconds = sessions, lease_seconds

    async def claim(self) -> OutboxClaim | None:
        async with self.sessions.begin() as session:
            now = datetime.now(UTC)
            row = await session.scalar(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.published_at.is_(None),
                    NotificationOutbox.available_at <= now,
                )
                .order_by(NotificationOutbox.available_at, NotificationOutbox.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return None
            row.lease_token = uuid4()
            row.available_at = now + timedelta(seconds=self.lease_seconds)
            row.attempts += 1
            return OutboxClaim(
                TaskWakeup(row.id, row.task_id, row.revision, row.created_at), row.lease_token
            )

    async def published(self, claim: OutboxClaim) -> None:
        async with self.sessions.begin() as session:
            await session.execute(
                update(NotificationOutbox)
                .where(
                    NotificationOutbox.id == claim.event.event_id,
                    NotificationOutbox.lease_token == claim.token,
                    NotificationOutbox.published_at.is_(None),
                )
                .values(published_at=datetime.now(UTC), lease_token=None, last_error=None)
            )

    async def retry(self, claim: OutboxClaim, error_type: str) -> None:
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.id == claim.event.event_id,
                    NotificationOutbox.lease_token == claim.token,
                    NotificationOutbox.published_at.is_(None),
                )
                .with_for_update()
            )
            if row is not None:
                row.lease_token = None
                row.last_error = error_type[:100]
                row.available_at = datetime.now(UTC) + timedelta(
                    seconds=min(2 ** min(row.attempts, 9), 300)
                )

    async def prune(self) -> None:
        async with self.sessions.begin() as session:
            expired = (
                select(NotificationOutbox.id)
                .where(NotificationOutbox.published_at < datetime.now(UTC) - timedelta(days=7))
                .limit(1000)
            )
            await session.execute(
                delete(NotificationOutbox).where(NotificationOutbox.id.in_(expired))
            )

    async def backlog(self) -> tuple[int, float]:
        async with self.sessions() as session:
            count, oldest = (
                await session.execute(
                    select(func.count(), func.min(NotificationOutbox.created_at)).where(
                        NotificationOutbox.published_at.is_(None)
                    )
                )
            ).one()
            return count, max(0, (datetime.now(UTC) - oldest).total_seconds()) if oldest else 0
