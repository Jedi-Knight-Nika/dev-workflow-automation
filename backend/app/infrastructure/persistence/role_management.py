import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.role_management import (
    RoleConflict,
    RoleNotFound,
    RoleView,
    SaveRoleCommand,
)
from app.db.models import AIAgent, Role
from app.domain.roles import Role as DomainRole


class SqlAlchemyRoleManagementWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[RoleView]:
        items = list(
            (
                await self.session.scalars(
                    select(Role)
                    .where(Role.archived_at.is_(None))
                    .order_by(Role.built_in.desc(), Role.name)
                )
            ).all()
        )
        counts = await self._agent_counts(tuple(item.id for item in items))
        return [self._view(item, counts.get(item.id, (0, 0))) for item in items]

    async def get(self, role_id: uuid.UUID) -> RoleView | None:
        item = await self.session.get(Role, role_id)
        if item is None or item.archived_at:
            return None
        counts = await self._agent_counts((item.id,))
        return self._view(item, counts.get(item.id, (0, 0)))

    async def create(self, command: SaveRoleCommand, *, built_in: bool = False) -> RoleView:
        self._validate(command)
        item = Role(**self._values(command), built_in=built_in)
        self.session.add(item)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise RoleConflict("A role with this name already exists") from exc
        return self._view(item, (0, 0))

    async def update(self, role_id: uuid.UUID, command: SaveRoleCommand) -> RoleView:
        item = await self.session.get(Role, role_id)
        if item is None or item.archived_at:
            raise RoleNotFound("Role not found")
        if item.built_in:
            raise RoleConflict("Built-in roles are immutable; clone this role first")
        self._validate(command)
        for key, value in self._values(command).items():
            setattr(item, key, value)
        item.version += 1
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise RoleConflict("A role with this name already exists") from exc
        counts = await self._agent_counts((item.id,))
        return self._view(item, counts.get(item.id, (0, 0)))

    async def clone(self, role_id: uuid.UUID, name: str) -> RoleView:
        source = await self.session.get(Role, role_id)
        if source is None or source.archived_at:
            raise RoleNotFound("Role not found")
        command = SaveRoleCommand(
            name,
            source.category,
            source.description,
            source.system_instructions,
            tuple(source.capabilities),
            tuple(source.permissions),
            tuple(source.allowed_results),
            tuple(uuid.UUID(v) for v in source.knowledge_collection_ids),
            source.default_provider,
            source.default_model,
            source.default_reasoning_effort,
            source.default_timeout_minutes,
            source.default_max_retries,
            True,
        )
        return await self.create(command)

    async def disable(self, role_id: uuid.UUID) -> RoleView:
        item = await self.session.get(Role, role_id)
        if item is None or item.archived_at:
            raise RoleNotFound("Role not found")
        item.enabled = False
        item.version += 1
        await self.session.commit()
        counts = await self._agent_counts((item.id,))
        return self._view(item, counts.get(item.id, (0, 0)))

    async def delete(self, role_id: uuid.UUID) -> None:
        item = await self.session.get(Role, role_id)
        if item is None or item.archived_at:
            raise RoleNotFound("Role not found")
        if item.built_in:
            raise RoleConflict("Built-in roles cannot be deleted")
        if await self.session.scalar(
            select(func.count()).select_from(AIAgent).where(AIAgent.role_id == role_id)
        ):
            raise RoleConflict("Reassign or delete agents using this role first")
        item.enabled = False
        item.archived_at = datetime.now(UTC)
        await self.session.commit()

    async def _agent_counts(
        self, role_ids: tuple[uuid.UUID, ...]
    ) -> dict[uuid.UUID, tuple[int, int]]:
        if not role_ids:
            return {}
        rows = (
            await self.session.execute(
                select(
                    AIAgent.role_id,
                    func.count().filter(AIAgent.enabled.is_(True)),
                    func.count().filter(AIAgent.enabled.is_(False)),
                )
                .where(AIAgent.role_id.in_(role_ids))
                .group_by(AIAgent.role_id)
            )
        ).all()
        return {
            role_id: (int(active_count), int(inactive_count))
            for role_id, active_count, inactive_count in rows
        }

    @staticmethod
    def _view(item: Role, agent_counts: tuple[int, int]) -> RoleView:
        active_agents, inactive_agents = agent_counts
        return RoleView(
            item.id,
            item.name,
            item.category,
            item.description,
            item.system_instructions,
            tuple(item.capabilities),
            tuple(item.permissions),
            tuple(item.allowed_results),
            tuple(uuid.UUID(v) for v in item.knowledge_collection_ids),
            item.default_provider,
            item.default_model,
            item.default_reasoning_effort,
            item.default_timeout_minutes,
            item.default_max_retries,
            item.enabled,
            item.built_in,
            item.version,
            active_agents,
            inactive_agents,
            active_agents + inactive_agents,
            item.created_at,
            item.updated_at,
        )

    @staticmethod
    def _values(c: SaveRoleCommand) -> dict[str, object]:
        return {
            "name": c.name.strip(),
            "category": c.category,
            "description": c.description.strip(),
            "system_instructions": c.system_instructions.strip(),
            "capabilities": list(c.capabilities),
            "permissions": list(c.permissions),
            "allowed_results": list(c.allowed_results),
            "knowledge_collection_ids": [str(v) for v in c.knowledge_collection_ids],
            "default_provider": c.default_provider,
            "default_model": c.default_model,
            "default_reasoning_effort": c.default_reasoning_effort,
            "default_timeout_minutes": c.default_timeout_minutes,
            "default_max_retries": c.default_max_retries,
            "enabled": c.enabled,
        }

    @staticmethod
    def _validate(c: SaveRoleCommand) -> None:
        DomainRole(
            uuid.uuid4(),
            c.name,
            c.category,
            c.system_instructions,
            c.capabilities,
            c.permissions,
            c.allowed_results,
            c.enabled,
        )
