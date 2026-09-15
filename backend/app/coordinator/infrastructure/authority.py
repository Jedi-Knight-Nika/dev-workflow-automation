"""Provider opt-in and actor authorization shared by admission and effects."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.coordinator.infrastructure.models import CoordinatorEvent
from app.engineering.infrastructure.task_models import Task
from app.intake.infrastructure.authorization import actor_allowed
from app.platform.configuration.settings import get_settings


def coordination_mode(provider: str) -> str:
    settings = get_settings()
    return settings.coordinator_mode if provider in settings.coordinator_providers else "off"


async def authorized(session: AsyncSession, task: Task, event: CoordinatorEvent) -> bool:
    if event.provider == "dashboard":
        return event.actor == "local-operator"
    if event.provider == "engineering":
        return event.actor == "engineering"
    return await actor_allowed(
        session, task, event.provider, event.actor, actor_type=event.context.get("actor_type")
    )
