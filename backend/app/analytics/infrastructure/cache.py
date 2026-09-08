import asyncio
from time import monotonic
from typing import Any
from uuid import UUID

from app.analytics.application.ports import AnalyticsQueries


class CachedAnalyticsQueries:
    """Single-flight bounded cache so a dashboard's cards share one DB cohort."""

    def __init__(self, inner: AnalyticsQueries) -> None:
        self.inner = inner
        self.cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
        self.lock = asyncio.Lock()

    async def _read(self, method: str, *args: Any) -> Any:
        key = (method, *args)
        async with asyncio.timeout(12), self.lock:
            cached = self.cache.get(key)
            if cached and monotonic() - cached[0] < 20:
                return cached[1]
            result = await getattr(self.inner, method)(*args)
            if len(self.cache) >= 128:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = monotonic(), result
            return result

    async def dashboard(self, days: int, team_id: UUID | None = None) -> dict[str, Any]:
        return dict(await self._read("dashboard", days, team_id))

    async def task(self, task_id: UUID) -> dict[str, Any] | None:
        result = await self._read("task", task_id)
        return dict(result) if result is not None else None

    async def forecast_task(self, task_id: UUID) -> dict[str, Any] | None:
        result = await self._read("forecast_task", task_id)
        return dict(result) if result is not None else None

    async def forecast_queue(self, team_id: UUID | None = None) -> dict[str, Any]:
        return dict(await self._read("forecast_queue", team_id))

    async def forecast_period(self, days: int) -> dict[str, Any]:
        return dict(await self._read("forecast_period", days))

    async def forecast_accuracy(self) -> dict[str, Any]:
        return dict(await self._read("forecast_accuracy"))
