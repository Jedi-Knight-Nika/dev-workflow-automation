from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.intake.infrastructure.github_events import process_next_github_delivery
from app.intake.infrastructure.linear_events import process_next_linear_delivery
from app.intake.infrastructure.review_text import process_review_text
from app.intake.infrastructure.source_deliveries import process_source_delivery
from app.platform.configuration.settings import Settings


class SqlAlchemyDeliveryProcessor:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], settings: Settings
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def process_linear(self) -> bool:
        async with self._session_factory() as session:
            source = await process_source_delivery(session)
            linear = await process_next_linear_delivery(session)
        return source or linear

    async def process_github(self) -> bool:
        async with self._session_factory() as session:
            return await process_next_github_delivery(session)

    async def process_review_text(self) -> bool:
        return await process_review_text(self._session_factory, self._settings)
