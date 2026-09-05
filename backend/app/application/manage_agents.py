from app.application.ports.agent_configuration import (
    AgentConfigCommand,
    AgentConfigurationWorkflow,
    AgentView,
)


class ManageAgents:
    def __init__(self, workflow: AgentConfigurationWorkflow) -> None:
        self._workflow = workflow

    async def list(self) -> list[AgentView]:
        return await self._workflow.list()

    async def update(self, command: AgentConfigCommand) -> AgentView:
        return await self._workflow.update(command)
