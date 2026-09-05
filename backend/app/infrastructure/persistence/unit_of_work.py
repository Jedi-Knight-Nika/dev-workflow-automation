from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.unit_of_work import EventRepository, JobRepository, TaskRepository
from app.infrastructure.persistence.repositories import (
    SqlAlchemyEventRepository,
    SqlAlchemyJobRepository,
    SqlAlchemyTaskRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.tasks: TaskRepository = SqlAlchemyTaskRepository(session)
        self.jobs: JobRepository = SqlAlchemyJobRepository(session)
        self.events: EventRepository = SqlAlchemyEventRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
