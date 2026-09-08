"""Durable tracker-status outbox. No AI, workflow graph or guessed list names."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import DateTime, ForeignKey, Index, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.delivery.domain.status import semantic_status
from app.platform.persistence.base import Base, utcnow


class ExternalStatusSync(Base):
    __tablename__ = "external_status_syncs"
    __table_args__ = (Index("ix_external_status_due", "status", "next_attempt_at"),)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    lifecycle_version: Mapped[int]
    semantic_status: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_error: Mapped[str | None] = mapped_column(String(255))


async def enqueue_status(
    session: AsyncSession, task_id: UUID, version: int, status: str, stage: str
) -> None:
    # Caller holds the Task lock, consistently preceding the outbox lock.
    row = await session.get(ExternalStatusSync, task_id, with_for_update=True)
    desired = semantic_status(status, stage)
    if row is None:
        session.add(
            ExternalStatusSync(task_id=task_id, lifecycle_version=version, semantic_status=desired)
        )
    else:
        row.lifecycle_version = version
        if row.semantic_status == desired and row.status in {"PENDING", "SYNCED"}:
            return
        row.semantic_status, row.status = desired, "PENDING"
        row.attempts, row.next_attempt_at, row.last_error = 0, datetime.now(UTC), None


async def process_status_sync(sessions: async_sessionmaker[AsyncSession]) -> bool:
    # Imported after registry initialization: the outbox model has no DB facade dependency.
    from app.engineering.infrastructure.task_models import Task, TaskEvent
    from app.intake.infrastructure.linear_client import LinearClient
    from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
    from app.intake.infrastructure.trello_client import TrelloClient
    from app.platform.integrations.models import Integration
    from app.platform.security.crypto import cipher

    async with sessions.begin() as session:
        task_id = await session.scalar(
            select(ExternalStatusSync.task_id)
            .where(
                ExternalStatusSync.status == "PENDING",
                ExternalStatusSync.next_attempt_at <= datetime.now(UTC),
            )
            .order_by(ExternalStatusSync.next_attempt_at)
            .limit(1)
        )
        if task_id is None:
            return False
        task = await session.scalar(
            select(Task).where(Task.id == task_id).with_for_update(skip_locked=True)
        )
        if task is None:
            return False
        row = await session.get(ExternalStatusSync, task_id, with_for_update=True)
        if row is None or row.status != "PENDING":
            return False
        if task.archived_at:
            row.status = "SKIPPED"
            return True
        snapshot = await session.scalar(
            select(ExternalTaskSnapshot)
            .where(
                ExternalTaskSnapshot.task_id == task.id,
                ExternalTaskSnapshot.provider.in_(["trello", "linear"]),
            )
            .order_by(ExternalTaskSnapshot.synchronized_at.desc())
            .limit(1)
        )
        if snapshot is None:
            row.status = "NO_TRACKER"
            return True
        integration = await session.scalar(
            select(Integration).where(Integration.provider_name == snapshot.provider)
        )
        suffix = "list_id" if snapshot.provider == "trello" else "state_id"
        key = f"{row.semantic_status}_{suffix}"
        target = (integration.configuration or {}).get(key) if integration else None
        if (
            not integration
            or not integration.encrypted_credentials
            or not isinstance(target, str)
            or not target
        ):
            row.status, row.last_error = (
                "CONFIGURATION_REQUIRED",
                f"Configure {snapshot.provider} {key}",
            )
        else:
            row.attempts += 1
            try:
                if snapshot.state_id != target:
                    credential = cipher.decrypt(integration.encrypted_credentials)
                    # Setting an absolute state is idempotent if a response is lost.
                    async with asyncio.timeout(15):
                        if snapshot.provider == "trello":
                            await TrelloClient(credential).update_card_list(
                                snapshot.external_id, target
                            )
                        else:
                            await LinearClient(credential).update_issue_state(
                                snapshot.external_id, target
                            )
                    snapshot.state_id, snapshot.synchronized_at = target, datetime.now(UTC)
                row.status, row.last_error = "SYNCED", None
            except (
                httpx.HTTPError,
                TimeoutError,
                InvalidToken,
                ValueError,
                TypeError,
                RuntimeError,
            ) as exc:
                row.status = "FAILED" if row.attempts >= 5 else "PENDING"
                row.last_error = f"Tracker status update failed: {type(exc).__name__}"
                row.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(60 * 2**row.attempts, 1800)
                )
        session.add(
            TaskEvent(
                task_id=task.id,
                source="engineering",
                event_type="ENGINEERING_EXTERNAL_STATUS_SYNC",
                payload={
                    "provider": snapshot.provider,
                    "semantic_status": row.semantic_status,
                    "status": row.status,
                    "error": row.last_error,
                    "lifecycle_version": row.lifecycle_version,
                },
            )
        )
    return True
