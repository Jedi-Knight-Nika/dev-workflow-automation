from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyReadinessProbe:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check(self) -> None:
        await self._session.execute(text("SELECT 1"))
