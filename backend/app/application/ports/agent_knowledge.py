import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AgentKnowledgeView:
    id: uuid.UUID
    role: str
    title: str
    content: str
    chunk_count: int
    created_at: datetime


class AgentKnowledgeWorkflow(Protocol):
    async def list(self, role: str) -> list[AgentKnowledgeView]: ...
    async def create(self, role: str, title: str, content: str) -> AgentKnowledgeView: ...
    async def delete(self, role: str, source_id: uuid.UUID) -> bool: ...
