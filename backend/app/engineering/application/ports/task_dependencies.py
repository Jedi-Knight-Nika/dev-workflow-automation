from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TaskDependencyView:
    id: UUID
    title: str
    status: str


class TaskDependencies(Protocol):
    async def replace(
        self, task_id: UUID, prerequisites: tuple[UUID, ...], expected: tuple[UUID, ...]
    ) -> None: ...
