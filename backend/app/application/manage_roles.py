import uuid

from app.application.ports.role_management import (
    RoleManagementWorkflow,
    RoleNotFound,
    RoleView,
    SaveRoleCommand,
)


class ManageRoles:
    def __init__(self, workflow: RoleManagementWorkflow) -> None:
        self.workflow = workflow

    async def list(self) -> list[RoleView]:
        return await self.workflow.list()

    async def get(self, role_id: uuid.UUID) -> RoleView:
        role = await self.workflow.get(role_id)
        if role is None:
            raise RoleNotFound("Role not found")
        return role

    async def create(self, command: SaveRoleCommand) -> RoleView:
        return await self.workflow.create(command)

    async def update(self, role_id: uuid.UUID, command: SaveRoleCommand) -> RoleView:
        return await self.workflow.update(role_id, command)

    async def clone(self, role_id: uuid.UUID, name: str) -> RoleView:
        return await self.workflow.clone(role_id, name)

    async def disable(self, role_id: uuid.UUID) -> RoleView:
        return await self.workflow.disable(role_id)

    async def delete(self, role_id: uuid.UUID) -> None:
        await self.workflow.delete(role_id)
