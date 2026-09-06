import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class TaskMessageView:
    id: int
    task_id: uuid.UUID
    job_id: uuid.UUID | None
    agent_id: uuid.UUID | None
    author_type: str
    author_name: str
    author_role: str | None
    kind: str
    body: str
    context: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TaskMessagePage:
    items: list[TaskMessageView]
    next_before_id: int | None


class TaskConversationStore(Protocol):
    async def list_messages(
        self, task_id: uuid.UUID, limit: int, before_id: int | None
    ) -> TaskMessagePage: ...

    async def add_user_message(self, task_id: uuid.UUID, body: str) -> TaskMessageView: ...
