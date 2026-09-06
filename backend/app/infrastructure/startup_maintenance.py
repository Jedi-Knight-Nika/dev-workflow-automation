from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.git.workspaces import cleanup_archived_workspaces
from app.infrastructure.persistence.job_operations import recover_expired_jobs
from app.infrastructure.reconciliation import reconcile_startup


class SqlAlchemyStartupMaintenance:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        workspace_root: Path,
        archived_workspace_retention_days: int,
    ) -> None:
        self._session_factory = session_factory
        self._workspace_root = workspace_root
        self._archived_workspace_retention_days = archived_workspace_retention_days

    async def recover_and_reconcile(self) -> None:
        async with self._session_factory() as session:
            await recover_expired_jobs(session)
            await reconcile_startup(session)
            await cleanup_archived_workspaces(
                session, self._workspace_root, self._archived_workspace_retention_days
            )
