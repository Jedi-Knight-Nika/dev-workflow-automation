from datetime import UTC, datetime, timedelta

import pytest

from app.application.ports.worker_queries import WorkerSnapshot
from app.application.query_workers import QueryWorkers


class FakeWorkerQueries:
    def __init__(self, workers: list[WorkerSnapshot]) -> None:
        self.workers = workers

    async def list(self) -> list[WorkerSnapshot]:
        return self.workers


@pytest.mark.asyncio
async def test_worker_online_status_uses_heartbeat_policy() -> None:
    now = datetime.now(UTC)
    recent = WorkerSnapshot(
        "recent", "host", 1, "ONLINE", ["jobs"], now, now - timedelta(seconds=29), None
    )
    stale = WorkerSnapshot(
        "stale", "host", 2, "ONLINE", ["jobs"], now, now - timedelta(seconds=31), None
    )
    stopped = WorkerSnapshot("stopped", "host", 3, "STOPPED", [], now, now, now)

    workers = await QueryWorkers(FakeWorkerQueries([recent, stale, stopped]), 10).execute(now=now)

    assert [worker.online for worker in workers] == [True, False, False]
