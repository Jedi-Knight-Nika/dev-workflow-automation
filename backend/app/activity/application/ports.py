from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class ActivityProjection(Protocol):
    async def project(self) -> int: ...


class ActivityMaintenance(Protocol):
    async def collect(self) -> None: ...
    async def expire(self) -> None: ...


@dataclass(frozen=True)
class ActivityScope:
    kind: str = "workspace"
    id: str | None = None


@dataclass(frozen=True)
class ActivityWindow:
    scope: ActivityScope
    start: datetime
    end: datetime
    detail: int = 2


class ActivityQueries(Protocol):
    async def projection_status(self) -> dict[str, Any]: ...

    async def preflight(self, window: ActivityWindow) -> dict[str, Any]: ...

    async def events(
        self, window: ActivityWindow, after: int, through: int | None, limit: int
    ) -> dict[str, Any]: ...

    async def baseline(self, window: ActivityWindow, through: int) -> dict[str, Any]: ...

    async def choices(self) -> dict[str, Any]: ...

    async def coverage(self, window: ActivityWindow) -> dict[str, Any]: ...

    async def capacity(self, window: ActivityWindow, through: int) -> dict[str, Any]: ...

    async def aggregate(self, window: ActivityWindow, through: int) -> dict[str, Any]: ...

    async def inspect(
        self, window: ActivityWindow, sequence: int, through: int
    ) -> dict[str, Any]: ...


class ActivityMonitor(Protocol):
    def stream_open(self, resumed: bool) -> None: ...
    def stream_close(self) -> None: ...
    def client_report(self, report: dict[str, float | int | None]) -> None: ...
