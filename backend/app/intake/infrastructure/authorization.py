from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.infrastructure.task_models import Task
from app.platform.configuration.settings import get_settings
from app.platform.integrations.models import Integration
from app.teams.infrastructure.automation import read_policy


async def actor_allowed(
    session: AsyncSession, task: Task, provider: str, actor: str, *, actor_type: str | None = None
) -> bool:
    if not actor or task.team_id is None:
        return False
    if provider == "github":
        policy = await read_policy(session, task.team_id)
        return actor_type != "Bot" and (
            actor in policy.authorized_reviewer_ids
            or (policy.reviewer_scope == "any_human" and actor_type == "User")
        )
    if provider == "slack":
        return any(
            route.get("team_id") == str(task.team_id)
            and route.get("repository_id") == str(task.repository_id)
            and actor in route.get("actor_ids", "").split(",")
            for route in get_settings().slack_team_routes.values()
        )
    if provider not in {"trello", "linear"}:
        return False
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == provider)
    )
    return bool(integration and actor in (integration.configuration or {}).get("v2_actor_ids", []))
