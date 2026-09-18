"""Notification contracts; messages never grant execution authority."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class PublicationFailed(RuntimeError):
    """The destination did not confirm delivery; the outbox must retain the event."""


@dataclass(frozen=True)
class TaskWakeup:
    event_id: UUID
    task_id: UUID
    revision: int
    occurred_at: datetime


@dataclass(frozen=True)
class OutboxClaim:
    event: TaskWakeup
    token: UUID


class EventPublisher(Protocol):
    async def publish(self, event: TaskWakeup) -> None:
        """Return only when delivery to the destination queue is confirmed."""
        ...


class EventOutbox(Protocol):
    async def claim(self) -> OutboxClaim | None:
        """Atomically acquire a recoverable lease; close the transaction before returning."""
        ...

    async def published(self, claim: OutboxClaim) -> None: ...
    async def retry(self, claim: OutboxClaim, error_type: str) -> None: ...
