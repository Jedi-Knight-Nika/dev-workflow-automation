import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorkflowDefinition, WorkflowNode


async def role_allows_integration(
    session: AsyncSession, role: str, integration_id: uuid.UUID, team_id: uuid.UUID | None = None
) -> bool:
    statement = select(WorkflowNode).where(
        WorkflowNode.role == role, WorkflowNode.enabled.is_(True)
    )
    if team_id is not None:
        statement = statement.join(
            WorkflowDefinition, WorkflowDefinition.id == WorkflowNode.workflow_id
        ).where(WorkflowDefinition.team_id == team_id)
    nodes = list((await session.scalars(statement)).all())
    explicitly_configured = [node for node in nodes if node.integration_ids]
    if not explicitly_configured:
        return True
    return any(str(integration_id) in node.integration_ids for node in explicitly_configured)
