from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.coordinator.domain.protocol import Decision


class SituationChanged(ValueError):
    """Completed engineering changes require fresh evidence for retained feedback."""


class ConversationUnavailable(RuntimeError):
    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.error_type = error_type


@dataclass(frozen=True)
class OutboundDelivery:
    action_id: UUID
    task_id: UUID
    provider: str
    message: str
    kind: str
    attempted_at: datetime


@dataclass(frozen=True)
class DeliveryClaim:
    handled: bool
    delivery: OutboundDelivery | None = None


class CoordinationActions(Protocol):
    """Atomic effects and durable delivery claims; network operations are outside this port."""

    async def execute_one(self) -> bool: ...
    async def claim_delivery(self) -> DeliveryClaim: ...
    async def complete_delivery(self, delivery: OutboundDelivery, reference: str) -> None: ...
    async def fail_delivery(
        self, delivery: OutboundDelivery, reason: str, *, reconcile: bool
    ) -> None: ...
    async def claim_reconciliation(self) -> OutboundDelivery | None: ...
    async def complete_reconciliation(
        self, delivery: OutboundDelivery, reference: str | None, error: str
    ) -> None: ...
    async def recover(self) -> None: ...


class CoordinationRuns(Protocol):
    """Atomic claims/results; implementations own locking, revisions and recovery."""

    async def claim(self) -> tuple[UUID, UUID, str, dict[str, Any]] | None: ...
    async def ensure_authorized(self, run_id: UUID) -> None: ...
    async def complete(
        self, run_id: UUID, task_id: UUID, decision: Decision, packet: dict[str, Any]
    ) -> None: ...
    async def fail(self, run_id: UUID, reason: str, *, superseded: bool) -> None: ...
    async def recover(self) -> None: ...


class DecisionModel(Protocol):
    async def decide(self, run_id: UUID, packet: dict[str, Any], call: int) -> Decision: ...


class ConversationGateway(Protocol):
    async def read(self, task_id: UUID, provider: str, tool: str) -> dict[str, Any]: ...
    async def reply(self, task_id: UUID, provider: str, message: str, action_id: UUID) -> str: ...
    async def request_review(self, task_id: UUID, action_id: UUID) -> str: ...
    async def reconcile(
        self,
        task_id: UUID,
        provider: str,
        message: str,
        action_id: UUID,
        attempted_at: datetime,
        kind: str,
    ) -> str | None: ...


class CoordinationAdministration(Protocol):
    async def task(self, task_id: UUID) -> dict[str, Any]: ...
    async def queue(self, team_id: UUID | None = None, offset: int = 0) -> dict[str, Any]: ...
    async def respond(self, task_id: UUID, request_id: UUID, answer: str) -> None: ...
    async def reconcile(self, task_id: UUID, action_id: UUID) -> None: ...
    async def review_action(self, task_id: UUID, action_id: UUID, verdict: str) -> None: ...
    async def priority(self, task_id: UUID, priority: int) -> None: ...
