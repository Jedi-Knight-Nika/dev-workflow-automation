import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorkflowNode


async def role_allows_integration(
    session: AsyncSession, role: str, integration_id: uuid.UUID
) -> bool:
    nodes = list(
        (
            await session.scalars(
                select(WorkflowNode).where(
                    WorkflowNode.role == role, WorkflowNode.enabled.is_(True)
                )
            )
        ).all()
    )
    explicitly_configured = [node for node in nodes if node.integration_ids]
    if not explicitly_configured:
        return True
    return any(str(integration_id) in node.integration_ids for node in explicitly_configured)
