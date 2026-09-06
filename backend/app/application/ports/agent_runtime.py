import uuid
from typing import Any, Protocol


class AgentRuntimeNotFound(Exception):
    pass


class AgentRuntimeStore(Protocol):
    async def effective(self, agent_id: uuid.UUID) -> dict[str, Any]: ...
    async def update(self, agent_id: uuid.UUID, overrides: dict[str, Any]) -> dict[str, Any]: ...
    async def reset(self, agent_id: uuid.UUID) -> dict[str, Any]: ...
