from datetime import UTC, datetime

import pytest

from app.application.manage_agents import ManageAgents
from app.application.ports.agent_configuration import AgentConfigCommand, AgentView
from app.domain.agents import agent_status


class FakeAgentWorkflow:
    def __init__(self, agent: AgentView) -> None:
        self.agent = agent
        self.command: AgentConfigCommand | None = None

    async def list(self) -> list[AgentView]:
        return [self.agent]

    async def update(self, command: AgentConfigCommand) -> AgentView:
        self.command = command
        return self.agent


@pytest.mark.asyncio
async def test_agent_management_delegates_reads_and_updates() -> None:
    agent = AgentView("THINKER", True, "openai", "model", {}, datetime.now(UTC), "READY")
    workflow = FakeAgentWorkflow(agent)
    manager = ManageAgents(workflow)
    command = AgentConfigCommand("THINKER", True, "openai", "model", {})

    assert await manager.list() == [agent]
    assert await manager.update(command) is agent
    assert workflow.command == command


def test_agent_status_policy_covers_operational_states() -> None:
    assert agent_status(enabled=False, model="m", active_jobs=1) == "DISABLED"
    assert agent_status(enabled=True, model="", active_jobs=0) == "NEEDS_CONFIGURATION"
    assert agent_status(enabled=True, model="m", active_jobs=1) == "RUNNING"
    assert agent_status(enabled=True, model="m", active_jobs=0) == "READY"
