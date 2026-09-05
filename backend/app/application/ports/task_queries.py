import uuid
from typing import Protocol

from app.domain.tasks import Task


class TaskQueries(Protocol):
    async def list(self, limit: int) -> list[Task]: ...
    async def get(self, task_id: uuid.UUID) -> Task | None: ...
