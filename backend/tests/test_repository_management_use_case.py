import uuid

import pytest

from app.application.manage_repositories import ManageRepositories
from app.application.ports.repository_management import CreateRepositoryCommand, RepositoryView


class FakeRepositoryWorkflow:
    def __init__(self) -> None:
        self.deleted_id: uuid.UUID | None = None

    async def list(self) -> list[RepositoryView]:
        return []

    async def create(self, command: CreateRepositoryCommand) -> RepositoryView:
        raise NotImplementedError

    async def set_enabled(self, repository_id: uuid.UUID, enabled: bool) -> RepositoryView:
        raise NotImplementedError

    async def queue_index(self, repository_id: uuid.UUID) -> RepositoryView:
        raise NotImplementedError

    async def delete(self, repository_id: uuid.UUID) -> None:
        self.deleted_id = repository_id


@pytest.mark.asyncio
async def test_repository_management_delegates_deletion() -> None:
    workflow = FakeRepositoryWorkflow()
    repository_id = uuid.uuid4()

    await ManageRepositories(workflow).delete(repository_id)

    assert workflow.deleted_id == repository_id
