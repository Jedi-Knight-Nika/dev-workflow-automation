import uuid

from app.application.ports.task_conversation import (
    TaskConversationStore,
    TaskMessagePage,
    TaskMessageView,
)


class QueryTaskConversation:
    def __init__(self, store: TaskConversationStore) -> None:
        self._store = store

    async def execute(
        self, task_id: uuid.UUID, limit: int, before_id: int | None
    ) -> TaskMessagePage:
        return await self._store.list_messages(task_id, limit, before_id)


class AddTaskMessage:
    def __init__(self, store: TaskConversationStore) -> None:
        self._store = store

    async def execute(self, task_id: uuid.UUID, body: str) -> TaskMessageView:
        normalized = body.strip()
        if not normalized:
            raise ValueError("Message cannot be empty")
        return await self._store.add_user_message(task_id, normalized)
