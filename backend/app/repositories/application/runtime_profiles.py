from typing import Any, Protocol
from uuid import UUID


class RepositoryRuntimes(Protocol):
    async def read(self, repository_id: UUID) -> dict[str, Any]: ...
    async def save(self, repository_id: UUID, values: dict[str, Any]) -> dict[str, Any]: ...
