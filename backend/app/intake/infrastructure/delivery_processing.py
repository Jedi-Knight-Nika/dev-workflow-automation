from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.delivery.infrastructure.rechecks import recheck_review
from app.delivery.infrastructure.status_sync import process_status_sync
from app.intake.infrastructure.github_events import process_next_github_delivery
from app.intake.infrastructure.linear_events import process_next_linear_delivery
from app.intake.infrastructure.review_text import process_review_text
from app.intake.infrastructure.source_deliveries import process_source_delivery
from app.platform.configuration.settings import get_settings


class SqlAlchemyDeliveryProcessor:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def process_linear(self) -> bool:
        async with self._session_factory() as session:
            source = await process_source_delivery(session)
            linear = await process_next_linear_delivery(session)
        synced = await process_status_sync(self._session_factory)
        return source or linear or synced

    async def process_github(self) -> bool:
        async with self._session_factory() as session:
            processed = await process_next_github_delivery(session)
        interpreted = await process_review_text(self._session_factory, get_settings())
        checked = await recheck_review(self._session_factory)
        return processed or interpreted or checked
