from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.observability.infrastructure.models import MonitoringConfiguration
from app.platform.configuration.models import SettingsAuditEvent


async def preferences(sessions: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    async with sessions() as session:
        row = await session.get(MonitoringConfiguration, "default")
        return dict(row.values) if row else {}


class SqlMonitoringAdministration:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def read(self) -> dict[str, Any]:
        return await preferences(self.sessions)

    async def save(self, values: dict[str, Any]) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(MonitoringConfiguration, "default", with_for_update=True)
            old = dict(row.values) if row else {}
            if row:
                row.values = values
            else:
                session.add(MonitoringConfiguration(id="default", values=values))
            session.add(
                SettingsAuditEvent(section="observability", old_values=old, new_values=values)
            )
