"""Adapter-neutral test setup hooks; production behavior is exercised through application ports."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.engineering.application.jobs import PhaseJobs, PhaseLease
from app.platform.messaging.application.ports import EventOutbox


@dataclass(frozen=True)
class PhaseSnapshot:
    status: str
    stage: str
    version: int
    queued_actions: tuple[str, ...]


class PhaseJobsHarness(Protocol):
    jobs: PhaseJobs

    async def seed(self) -> UUID: ...
    async def pause(self, task_id: UUID) -> None: ...
    async def expire(self, lease: PhaseLease) -> None: ...
    async def snapshot(self, task_id: UUID) -> PhaseSnapshot: ...


class OutboxHarness(Protocol):
    outbox: EventOutbox

    async def seed(self) -> UUID: ...
    async def make_due(self, event_id: UUID) -> None: ...
    async def is_published(self, event_id: UUID) -> bool: ...
