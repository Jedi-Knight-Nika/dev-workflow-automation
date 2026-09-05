from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.github_events import process_next_github_delivery
from app.infrastructure.linear_events import process_next_linear_delivery


class SqlAlchemyDeliveryProcessor:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def process_linear(self) -> bool:
        async with self._session_factory() as session:
            return await process_next_linear_delivery(session)

    async def process_github(self) -> bool:
        async with self._session_factory() as session:
            return await process_next_github_delivery(session)
