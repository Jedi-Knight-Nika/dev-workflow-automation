from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WorkerSnapshot:
    id: str
    hostname: str
    process_id: int
    status: str
    capabilities: list[str]
    started_at: datetime
    last_heartbeat: datetime
    stopped_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorkerView:
    id: str
    hostname: str
    process_id: int
    status: str
    online: bool
    capabilities: list[str]
    started_at: datetime
    last_heartbeat: datetime
    stopped_at: datetime | None


class WorkerQueries(Protocol):
    async def list(self) -> list[WorkerSnapshot]: ...
