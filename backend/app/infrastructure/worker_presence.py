import os
import socket
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import WorkerNode


class SqlAlchemyWorkerPresence:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], worker_id: str) -> None:
        self._session_factory = session_factory
        self._worker_id = worker_id

    async def _write(self, status: str) -> None:
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            worker = await session.get(WorkerNode, self._worker_id)
            if worker is None:
                worker = WorkerNode(
                    id=self._worker_id,
                    hostname=socket.gethostname(),
                    process_id=os.getpid(),
                    capabilities=["jobs", "linear", "indexing"],
                    started_at=now,
                )
                session.add(worker)
            worker.status = status
            worker.last_heartbeat = now
            worker.stopped_at = now if status == "STOPPED" else None
            await session.commit()

    async def mark_online(self) -> None:
        await self._write("ONLINE")

    async def mark_stopped(self) -> None:
        await self._write("STOPPED")
