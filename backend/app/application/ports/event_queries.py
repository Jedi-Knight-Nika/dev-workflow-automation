import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EventView:
    id: int
    task_id: uuid.UUID
    event_type: str


class EventQueries(Protocol):
    async def latest_id(self) -> int: ...

    async def after(self, event_id: int, limit: int) -> list[EventView]: ...
