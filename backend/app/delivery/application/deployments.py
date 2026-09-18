from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


class DeploymentQueries(Protocol):
    async def history(
        self, start: datetime, end: datetime, repository_id: UUID | None, limit: int
    ) -> dict[str, Any]: ...
