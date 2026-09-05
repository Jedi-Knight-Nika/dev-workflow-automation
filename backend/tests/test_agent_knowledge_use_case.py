import uuid
from datetime import UTC, datetime

import pytest

from app.application.manage_agent_knowledge import ManageAgentKnowledge
from app.application.ports.agent_knowledge import AgentKnowledgeView


class FakeAgentKnowledge:
    def __init__(self) -> None:
        self.item = AgentKnowledgeView(
            uuid.uuid4(), "THINKER", "Rules", "Use ports", 1, datetime.now(UTC)
        )
        self.deleted: tuple[str, uuid.UUID] | None = None

    async def list(self, role: str) -> list[AgentKnowledgeView]:
        return [self.item] if role == self.item.role else []

    async def create(self, role: str, title: str, content: str) -> AgentKnowledgeView:
        self.item = AgentKnowledgeView(uuid.uuid4(), role, title, content, 2, datetime.now(UTC))
        return self.item

    async def delete(self, role: str, source_id: uuid.UUID) -> bool:
        self.deleted = (role, source_id)
        return source_id == self.item.id


@pytest.mark.asyncio
async def test_agent_knowledge_management_uses_port_contract() -> None:
    gateway = FakeAgentKnowledge()
    use_case = ManageAgentKnowledge(gateway)

    created = await use_case.create("EXECUTOR", "Engineering rules", "Keep boundaries clean")

    assert created.role == "EXECUTOR"
    assert await use_case.list("EXECUTOR") == [created]
    assert await use_case.delete("EXECUTOR", created.id)
    assert gateway.deleted == ("EXECUTOR", created.id)
