import builtins
import uuid

from app.application.ports.notifications import NotificationStore, NotificationView, RaiseIncident


class ManageNotifications:
    def __init__(self, store: NotificationStore) -> None:
        self._store = store

    async def raise_incident(self, command: RaiseIncident) -> NotificationView | None:
        return await self._store.raise_incident(command)

    async def list(self, status: str | None, limit: int) -> list[NotificationView]:
        return await self._store.list_notifications(status, limit)

    async def unread_count(self) -> int:
        return await self._store.unread_count()

    async def mark(self, notification_id: uuid.UUID, action: str) -> NotificationView:
        return await self._store.mark(notification_id, action)

    async def incidents(self, status: str | None) -> builtins.list[dict[str, object]]:
        return await self._store.incidents(status)

    async def mark_incident(self, incident_id: uuid.UUID, action: str) -> dict[str, object]:
        return await self._store.mark_incident(incident_id, action)
