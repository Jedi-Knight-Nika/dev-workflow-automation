from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.infrastructure.job_queue import record_event, request_execution
from app.engineering.infrastructure.task_models import Task
from app.teams.infrastructure.routing import assign_routed_team


class SqlEngineeringIntake:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def created(
        self, task_id: UUID, provider: str, external_id: str, identifier: str
    ) -> None:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise LookupError("Imported task is missing")
        await assign_routed_team(self.session, task, reason=f"{provider}-reconciliation")
        await request_execution(self.session, task, actor="tracker:ingestion")
        event_type, key = (
            ("TASK_CREATED_FROM_TRELLO", "trello_card_id")
            if provider == "trello"
            else ("TASK_CREATED_FROM_LINEAR_RECONCILIATION", "linear_issue_id")
        )
        await record_event(
            self.session,
            task.id,
            event_type,
            {key: external_id, "identifier": identifier},
            source=provider,
        )
