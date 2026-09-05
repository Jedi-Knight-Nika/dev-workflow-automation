from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.event_queries import EventView
from app.db.models import TaskEvent


class SqlAlchemyEventQueries:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def latest_id(self) -> int:
        async with self._session_factory() as session:
            return int(await session.scalar(select(func.max(TaskEvent.id))) or 0)

    async def after(self, event_id: int, limit: int) -> list[EventView]:
        async with self._session_factory() as session:
            events = (
                await session.scalars(
                    select(TaskEvent)
                    .where(TaskEvent.id > event_id)
                    .order_by(TaskEvent.id)
                    .limit(limit)
                )
            ).all()
            return [EventView(item.id, item.task_id, item.event_type) for item in events]
