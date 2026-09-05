from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.worker_queries import WorkerSnapshot
from app.db.models import WorkerNode


class SqlAlchemyWorkerQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[WorkerSnapshot]:
        records = (
            await self._session.scalars(select(WorkerNode).order_by(WorkerNode.started_at.desc()))
        ).all()
        return [
            WorkerSnapshot(
                item.id,
                item.hostname,
                item.process_id,
                item.status,
                item.capabilities,
                item.started_at,
                item.last_heartbeat,
                item.stopped_at,
            )
            for item in records
        ]
