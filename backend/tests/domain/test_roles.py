import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.application.manage_roles import ManageRoles
from app.application.ports.role_management import RoleNotFound, RoleView, SaveRoleCommand
from app.domain.roles import Role
from app.worker import ResolvedAgentConfig, require_permission


def command(**changes: object) -> SaveRoleCommand:
    base = SaveRoleCommand(
        name="Security Reviewer",
        category="REVIEW",
        description="Reviews security boundaries",
        system_instructions="Report evidenced security problems.",
        capabilities=("CAN_REVIEW", "CAN_PRODUCE_FINDINGS"),
        permissions=("READ_REPOSITORY", "READ_DIFF", "RUN_TESTS"),
        allowed_results=("PASS", "FAIL_ACTIONABLE", "NEEDS_HUMAN"),
    )
    return replace(base, **changes)


def view(role_id: uuid.UUID) -> RoleView:
    now = datetime.now(UTC)
    value = command()
    return RoleView(
        role_id,
        value.name,
        value.category,
        value.description,
        value.system_instructions,
        value.capabilities,
        value.permissions,
        value.allowed_results,
        (),
        None,
        None,
        "default",
        30,
        2,
        True,
        False,
        1,
        0,
        0,
        0,
        now,
        now,
    )


class FakeRoles:
    def __init__(self) -> None:
        self.item = view(uuid.uuid4())

    async def list(self) -> list[RoleView]:
        return [self.item]

    async def get(self, role_id: uuid.UUID) -> RoleView | None:
        return self.item if role_id == self.item.id else None

    async def create(self, value: SaveRoleCommand, *, built_in: bool = False) -> RoleView:
        del value, built_in
        return self.item

    async def update(self, role_id: uuid.UUID, value: SaveRoleCommand) -> RoleView:
        del role_id, value
        return self.item

    async def clone(self, role_id: uuid.UUID, name: str) -> RoleView:
        del role_id, name
        return self.item

    async def disable(self, role_id: uuid.UUID) -> RoleView:
        del role_id
        return self.item

    async def delete(self, role_id: uuid.UUID) -> None:
        del role_id


def test_role_rejects_implementation_without_write_permission() -> None:
    with pytest.raises(ValueError, match="WRITE_REPOSITORY"):
        Role(
            uuid.uuid4(),
            "Executor",
            "EXECUTION",
            "Implement",
            ("CAN_IMPLEMENT",),
            ("READ_REPOSITORY",),
        )


@pytest.mark.asyncio
async def test_manage_roles_resolves_or_rejects_missing_role() -> None:
    workflow = FakeRoles()
    service = ManageRoles(workflow)
    assert (await service.get(workflow.item.id)).name == "Security Reviewer"
    with pytest.raises(RoleNotFound):
        await service.get(uuid.uuid4())


def test_runtime_permission_is_physically_enforced_for_role_agent() -> None:
    config = ResolvedAgentConfig(
        "openai", "model", "prompt", {}, (), role_id=uuid.uuid4(), permissions=("READ_DIFF",)
    )
    require_permission(config, "READ_DIFF")
    with pytest.raises(RuntimeError, match="WRITE_REPOSITORY"):
        require_permission(config, "WRITE_REPOSITORY")


def test_legacy_agent_remains_compatible_during_migration() -> None:
    config = ResolvedAgentConfig("openai", "model", "prompt", {}, ())
    require_permission(config, "WRITE_REPOSITORY")
