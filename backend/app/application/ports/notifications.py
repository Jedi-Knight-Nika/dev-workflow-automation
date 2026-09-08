import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

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
    async def raise_incident(
        self, command: RaiseIncident, *, commit: bool = True
    ) -> NotificationView | None: ...
    async def list_notifications(
        self, status: str | None, limit: int
    ) -> list[NotificationView]: ...
    async def unread_count(self) -> int: ...
    async def mark_all_read(self) -> int: ...
    async def mark(self, notification_id: uuid.UUID, action: str) -> NotificationView: ...
    async def incidents(self, status: str | None) -> list[dict[str, object]]: ...
    async def mark_incident(self, incident_id: uuid.UUID, action: str) -> dict[str, object]: ...


class TelegramGateway(Protocol):
    async def connect(self) -> dict[str, object]: ...
    async def configure(
        self, bot_token: str, webhook_base_url: str | None
    ) -> dict[str, object]: ...
    async def status(self) -> dict[str, object]: ...
    async def disconnect(self) -> None: ...
    async def webhook_secret(self) -> str | None: ...
    async def handle_update(self, update: dict[str, Any]) -> None: ...
