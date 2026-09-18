from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.activity.infrastructure.files import collect_files
from app.activity.infrastructure.retention import expire_file_details


class SqlActivityMaintenance:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        workspace_root: Path,
        *,
        collect_files_enabled: bool,
        retention_days: int,
    ) -> None:
        self.sessions, self.workspace_root = sessions, workspace_root
        self.collect_files_enabled, self.retention_days = collect_files_enabled, retention_days

    async def collect(self) -> None:
        if self.collect_files_enabled:
            await collect_files(self.sessions, self.workspace_root)

    async def expire(self) -> None:
        await expire_file_details(self.sessions, self.retention_days)
