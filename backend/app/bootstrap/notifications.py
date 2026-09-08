from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.notifications import TelegramGateway
from app.config import Settings, get_settings
from app.db.session import SessionLocal, get_session
from app.infrastructure.telegram import TelegramService


def telegram_gateway(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TelegramGateway:
    return TelegramService(session, settings)


async def deliver_pending() -> None:
    async with SessionLocal() as session:
        await TelegramService(session, get_settings()).deliver_pending()
