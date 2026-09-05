import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task
from app.domain.tasks import Task as DomainTask
from app.infrastructure.persistence.repositories import task_to_domain


class SqlAlchemyTaskQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, limit: int) -> list[DomainTask]:
        records = (
            await self._session.scalars(select(Task).order_by(Task.created_at.desc()).limit(limit))
        ).all()
        return [task_to_domain(record) for record in records]

    async def get(self, task_id: uuid.UUID) -> DomainTask | None:
        record = await self._session.get(Task, task_id)
        return task_to_domain(record) if record is not None else None
