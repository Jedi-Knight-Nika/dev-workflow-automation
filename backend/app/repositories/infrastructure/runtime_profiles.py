from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.infrastructure.models import Repository, RepositoryRuntimeProfile


class SqlRepositoryRuntimes:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], default_image: str) -> None:
        self.sessions, self.default_image = sessions, default_image

    async def read(self, repository_id: UUID) -> dict[str, Any]:
        async with self.sessions() as session:
            if await session.get(Repository, repository_id) is None:
                raise LookupError("Repository not found")
            row = await session.get(RepositoryRuntimeProfile, repository_id)
            if row is None:
                return {
                    "repository_id": str(repository_id),
                    "developer_image_ref": self.default_image,
                    "validator_image_ref": self.default_image,
                    "validation_commands": [],
                    "image_digest": None,
                    "last_verified_at": None,
                }
            return {c.name: getattr(row, c.name) for c in row.__table__.columns}

    async def save(self, repository_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            if await session.get(Repository, repository_id) is None:
                raise LookupError("Repository not found")
            row = await session.get(RepositoryRuntimeProfile, repository_id, with_for_update=True)
            if row is None:
                session.add(RepositoryRuntimeProfile(repository_id=repository_id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                row.last_verified_at = None
                row.image_digest = None
        return await self.read(repository_id)
