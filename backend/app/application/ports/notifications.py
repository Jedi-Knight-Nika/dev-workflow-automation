import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.notifications import NotificationSeverity


@dataclass(frozen=True, slots=True)
class RaiseIncident:
    fingerprint: str
    type: str
    severity: NotificationSeverity
    title: str
    summary: str
    team_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    action_target: str | None = None
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class NotificationView:
    id: uuid.UUID
    incident_id: uuid.UUID | None
    type: str
    severity: str
    title: str
    message: str
    status: str
    task_id: uuid.UUID | None
    action_target: str | None
    created_at: datetime


class NotificationStore(Protocol):
    async def raise_incident(self, command: RaiseIncident) -> NotificationView | None: ...
    async def list_notifications(
        self, status: str | None, limit: int
    ) -> list[NotificationView]: ...
    async def unread_count(self) -> int: ...
    async def mark(self, notification_id: uuid.UUID, action: str) -> NotificationView: ...
    async def incidents(self, status: str | None) -> list[dict[str, object]]: ...
    async def mark_incident(self, incident_id: uuid.UUID, action: str) -> dict[str, object]: ...
