from datetime import UTC, datetime

from app.platform.scheduling.availability import is_worker_online
from app.platform.scheduling.ports.worker_queries import WorkerQueries, WorkerView


class QueryWorkers:
    def __init__(self, queries: WorkerQueries, heartbeat_seconds: float) -> None:
        self._queries = queries
        self._heartbeat_seconds = heartbeat_seconds

    async def execute(self, *, now: datetime | None = None) -> list[WorkerView]:
        checked_at = now or datetime.now(UTC)
        return [
            WorkerView(
                worker.id,
                worker.hostname,
                worker.process_id,
                worker.status,
                is_worker_online(
                    status=worker.status,
                    last_heartbeat=worker.last_heartbeat,
                    now=checked_at,
                    heartbeat_seconds=self._heartbeat_seconds,
                ),
                worker.capabilities,
                worker.started_at,
                worker.last_heartbeat,
                worker.stopped_at,
            )
            for worker in await self._queries.list()
        ]
