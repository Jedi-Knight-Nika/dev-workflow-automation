import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.notifications import NotificationView, RaiseIncident
from app.db.models import Incident, Notification, NotificationDelivery, TelegramConnection
from app.domain.notifications import IncidentStatus, NotificationStatus, telegram_required


class SqlAlchemyNotificationStore:
    def __init__(self, session: AsyncSession, user_id: str = "local-user") -> None:
        self._session = session
        self._user_id = user_id

    async def raise_incident(
        self, command: RaiseIncident, *, commit: bool = True
    ) -> NotificationView | None:
        now = datetime.now(UTC)
        incident = await self._session.scalar(
            select(Incident).where(Incident.fingerprint == command.fingerprint).with_for_update()
        )
        if incident and incident.status != IncidentStatus.RESOLVED.value:
            incident.occurrence_count += 1
            incident.last_seen_at = now
            incident.summary = command.summary
            incident.metadata_json = command.metadata or {}
            if commit:
                await self._session.commit()
            return None
        if incident:
            incident.status = IncidentStatus.OPEN.value
            incident.severity = command.severity.value
            incident.title = command.title
            incident.summary = command.summary
            incident.first_seen_at = now
            incident.last_seen_at = now
            incident.resolved_at = None
            incident.acknowledged_at = None
            incident.occurrence_count = 1
            incident.root_resource_type = (
                str((command.metadata or {}).get("resource_type") or "") or None
            )
            incident.root_resource_id = (
                str((command.metadata or {}).get("resource_id") or "") or None
            )
        else:
            incident = Incident(
                fingerprint=command.fingerprint,
                type=command.type,
                severity=command.severity.value,
                team_id=command.team_id,
                task_id=command.task_id,
                job_id=command.job_id,
                title=command.title,
                summary=command.summary,
                root_resource_type=str((command.metadata or {}).get("resource_type") or "") or None,
                root_resource_id=str((command.metadata or {}).get("resource_id") or "") or None,
                metadata_json=command.metadata or {},
            )
            self._session.add(incident)
            await self._session.flush()
        notification = Notification(
            user_id=self._user_id,
            incident_id=incident.id,
            team_id=command.team_id,
            task_id=command.task_id,
            job_id=command.job_id,
            type=command.type,
            severity=command.severity.value,
            title=command.title,
            message=command.summary,
            action_type="OPEN" if command.action_target else None,
            action_target=command.action_target,
            metadata_json=command.metadata or {},
        )
        self._session.add(notification)
        await self._session.flush()
        self._session.add(
            NotificationDelivery(
                notification_id=notification.id,
                channel="IN_APP",
                recipient_ref=self._user_id,
                state="DELIVERED",
                attempt_count=1,
                delivered_at=now,
            )
        )
        if telegram_required(command.severity):
            connection = await self._session.scalar(
                select(TelegramConnection).where(
                    TelegramConnection.user_id == self._user_id,
                    TelegramConnection.enabled.is_(True),
                )
            )
            if connection:
                self._session.add(
                    NotificationDelivery(
                        notification_id=notification.id,
                        channel="TELEGRAM",
                        recipient_ref=connection.telegram_chat_id,
                    )
                )
        if commit:
            await self._session.commit()
        return self._view(notification)

    async def list_notifications(self, status: str | None, limit: int) -> list[NotificationView]:
        statement = select(Notification).where(Notification.user_id == self._user_id)
        if status:
            statement = statement.where(Notification.status == status)
        records = (
            await self._session.scalars(
                statement.order_by(Notification.created_at.desc()).limit(limit)
            )
        ).all()
        return [self._view(record) for record in records]

    async def unread_count(self) -> int:
        return int(
            await self._session.scalar(
                select(func.count(Notification.id)).where(
                    Notification.user_id == self._user_id,
                    Notification.status == NotificationStatus.UNREAD.value,
                )
            )
            or 0
        )

    async def mark(self, notification_id: uuid.UUID, action: str) -> NotificationView:
        record = await self._session.get(Notification, notification_id)
        if record is None or record.user_id != self._user_id:
            raise LookupError("Notification not found")
        now = datetime.now(UTC)
        if action == "read" and record.status == NotificationStatus.UNREAD.value:
            record.status, record.read_at = NotificationStatus.READ.value, now
        elif action == "acknowledge":
            record.status, record.acknowledged_at = NotificationStatus.ACKNOWLEDGED.value, now
            if record.incident_id:
                await self.mark_incident(record.incident_id, "acknowledge", commit=False)
        else:
            raise ValueError("Unsupported notification action")
        await self._session.commit()
        return self._view(record)

    async def incidents(self, status: str | None) -> list[dict[str, object]]:
        statement = select(Incident)
        if status:
            statement = statement.where(Incident.status == status)
        records = (
            await self._session.scalars(statement.order_by(Incident.last_seen_at.desc()))
        ).all()
        return [self._incident(record) for record in records]

    async def mark_incident(
        self, incident_id: uuid.UUID, action: str, *, commit: bool = True
    ) -> dict[str, object]:
        record = await self._session.get(Incident, incident_id)
        if record is None:
            raise LookupError("Incident not found")
        now = datetime.now(UTC)
        if action == "acknowledge":
            record.status, record.acknowledged_at = IncidentStatus.ACKNOWLEDGED.value, now
        elif action == "resolve":
            record.status, record.resolved_at = IncidentStatus.RESOLVED.value, now
        elif action == "mute":
            record.status = IncidentStatus.MUTED.value
        else:
            raise ValueError("Unsupported incident action")
        if commit:
            await self._session.commit()
        return self._incident(record)

    @staticmethod
    def _view(record: Notification) -> NotificationView:
        return NotificationView(
            record.id,
            record.incident_id,
            record.type,
            record.severity,
            record.title,
            record.message,
            record.status,
            record.task_id,
            record.action_target,
            record.created_at,
        )

    @staticmethod
    def _incident(record: Incident) -> dict[str, object]:
        return {
            "id": record.id,
            "fingerprint": record.fingerprint,
            "type": record.type,
            "severity": record.severity,
            "status": record.status,
            "team_id": record.team_id,
            "task_id": record.task_id,
            "job_id": record.job_id,
            "title": record.title,
            "summary": record.summary,
            "occurrence_count": record.occurrence_count,
            "metadata": record.metadata_json,
            "first_seen_at": record.first_seen_at,
            "last_seen_at": record.last_seen_at,
            "acknowledged_at": record.acknowledged_at,
            "resolved_at": record.resolved_at,
        }
