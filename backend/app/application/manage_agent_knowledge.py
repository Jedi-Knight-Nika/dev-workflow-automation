import uuid

from app.application.ports.agent_knowledge import AgentKnowledgeView, AgentKnowledgeWorkflow


class ManageAgentKnowledge:
    def __init__(self, workflow: AgentKnowledgeWorkflow) -> None:
        self._workflow = workflow

    async def list(self, role: str) -> list[AgentKnowledgeView]:
        return await self._workflow.list(role)

    async def create(self, role: str, title: str, content: str) -> AgentKnowledgeView:
        return await self._workflow.create(role, title, content)

    async def delete(self, role: str, source_id: uuid.UUID) -> bool:
        return await self._workflow.delete(role, source_id)
