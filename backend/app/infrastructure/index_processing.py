from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.indexing import process_queued_indexes


class SqlAlchemyIndexProcessor:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def process_next(self) -> bool:
        async with self._session_factory() as session:
            return bool(await process_queued_indexes(session))
