import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.repository_management import (
    CreateRepositoryCommand,
    ManagedRepositoryConflict,
    ManagedRepositoryNotFound,
    RepositoryView,
)
from app.db.models import AccountSettings, IndexStatus, Repository


class SqlAlchemyRepositoryManagementWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _view(self, item: Repository) -> RepositoryView:
        count = int(
            await self._session.scalar(
                text(
                    "SELECT count(*) FROM knowledge_chunks WHERE repository_id = :repository_id"
                ).bindparams(repository_id=item.id)
            )
            or 0
        )
        return RepositoryView(
            item.id,
            item.provider,
            item.external_repo_id,
            item.owner,
            item.name,
            item.clone_url,
            item.default_branch,
            item.enabled,
            item.local_path,
            item.latest_sha,
            item.indexed_sha,
            item.indexed_at,
            item.index_status.value,
            item.index_error,
            item.updated_at,
            "CLONED" if item.local_path and item.latest_sha else "NOT_CLONED",
            count,
        )

    async def list(self) -> list[RepositoryView]:
        items = (
            await self._session.scalars(
                select(Repository).order_by(Repository.owner, Repository.name)
            )
        ).all()
        return [await self._view(item) for item in items]

    async def create(self, command: CreateRepositoryCommand) -> RepositoryView:
        settings = await self._session.get(AccountSettings, "default")
        auto_index = settings is None or settings.auto_index_repositories
        item = Repository(
            provider=command.provider,
            external_repo_id=command.external_repo_id,
            owner=command.owner,
            name=command.name,
            clone_url=command.clone_url,
            default_branch=command.default_branch,
            index_status=IndexStatus.QUEUED if auto_index else IndexStatus.NOT_INDEXED,
            index_error=None,
        )
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return await self._view(item)

    async def _locked(self, repository_id: uuid.UUID) -> Repository:
        item = await self._session.get(Repository, repository_id, with_for_update=True)
        if item is None:
            raise ManagedRepositoryNotFound("Repository not found")
        return item

    async def set_enabled(self, repository_id: uuid.UUID, enabled: bool) -> RepositoryView:
        item = await self._locked(repository_id)
        item.enabled = enabled
        if enabled:
            item.index_status, item.index_error = IndexStatus.QUEUED, None
        await self._session.commit()
        return await self._view(item)

    async def queue_index(self, repository_id: uuid.UUID) -> RepositoryView:
        item = await self._locked(repository_id)
        if not item.enabled:
            raise ManagedRepositoryConflict("Repository is disabled")
        item.index_status, item.index_error = IndexStatus.QUEUED, None
        await self._session.commit()
        return await self._view(item)

    async def delete(self, repository_id: uuid.UUID) -> None:
        item = await self._locked(repository_id)
        await self._session.delete(item)
        await self._session.commit()
