import uuid
from typing import Any

from app.application.ports.agent_runtime import AgentRuntimeStore


class ManageAgentRuntime:
    def __init__(self, store: AgentRuntimeStore) -> None:
        self._store = store

    async def get(self, agent_id: uuid.UUID) -> dict[str, Any]:
        return await self._store.effective(agent_id)

    async def update(self, agent_id: uuid.UUID, overrides: dict[str, Any]) -> dict[str, Any]:
        return await self._store.update(agent_id, overrides)

    async def reset(self, agent_id: uuid.UUID) -> dict[str, Any]:
        return await self._store.reset(agent_id)
