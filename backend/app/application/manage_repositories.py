import uuid

from app.application.ports.repository_management import (
    CreateRepositoryCommand,
    RepositoryManagementWorkflow,
    RepositoryView,
)


class ManageRepositories:
    def __init__(self, workflow: RepositoryManagementWorkflow) -> None:
        self._workflow = workflow

    async def list(self) -> list[RepositoryView]:
        return await self._workflow.list()

    async def create(self, command: CreateRepositoryCommand) -> RepositoryView:
        return await self._workflow.create(command)

    async def set_enabled(self, repository_id: uuid.UUID, enabled: bool) -> RepositoryView:
        return await self._workflow.set_enabled(repository_id, enabled)

    async def queue_index(self, repository_id: uuid.UUID) -> RepositoryView:
        return await self._workflow.queue_index(repository_id)

    async def delete(self, repository_id: uuid.UUID) -> None:
        await self._workflow.delete(repository_id)
