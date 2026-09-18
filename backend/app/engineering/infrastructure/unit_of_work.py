from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.application.ports.unit_of_work import (
    EventRepository,
    TaskExecution,
    TaskRepository,
)
from app.engineering.infrastructure.repositories import (
    SqlAlchemyEventRepository,
    SqlAlchemyTaskRepository,
)
from app.engineering.infrastructure.start_task import SqlTaskExecution
from app.teams.application.ports.team_management import AssignTaskCommand
from app.teams.infrastructure.management import SqlAlchemyTeamManagementWorkflow


class SqlTaskAssignment:
    def __init__(self, session: AsyncSession) -> None:
        self._teams = SqlAlchemyTeamManagementWorkflow(session)

    async def assign(self, task_id: UUID, team_id: UUID) -> None:
        await self._teams.assign_in_transaction(
            AssignTaskCommand(task_id=task_id, team_id=team_id, reason="manual-creation")
        )


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.tasks: TaskRepository = SqlAlchemyTaskRepository(session)
        self.execution: TaskExecution = SqlTaskExecution(session)
        self.events: EventRepository = SqlAlchemyEventRepository(session)
        self.assignments = SqlTaskAssignment(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
