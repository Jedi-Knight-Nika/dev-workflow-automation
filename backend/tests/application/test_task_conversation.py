import uuid
from typing import cast

import pytest

from app.engineering.application.manage_task_conversation import (
    AddTaskMessage,
)
from app.engineering.application.ports.task_conversation import (
    TaskConversationStore,
    TaskMessageView,
)


class RecordingConversationStore:
    def __init__(self) -> None:
        self.body = ""

    async def add_user_message(
        self, task_id: uuid.UUID, body: str, reply_to_id: int | None
    ) -> TaskMessageView:
        self.body = body
        return cast(TaskMessageView, object())

    async def edit_user_message(
        self, task_id: uuid.UUID, message_id: int, body: str
    ) -> TaskMessageView:
        self.body = body
        return cast(TaskMessageView, object())

    async def toggle_reaction(
        self, task_id: uuid.UUID, message_id: int, reaction: str
    ) -> TaskMessageView:
        self.body = reaction
        return cast(TaskMessageView, object())


@pytest.mark.asyncio
async def test_user_message_is_trimmed_before_persistence() -> None:
    store = RecordingConversationStore()

    await AddTaskMessage(cast(TaskConversationStore, store)).execute(uuid.uuid4(), "  context  ")

    assert store.body == "context"


@pytest.mark.asyncio
async def test_blank_user_message_is_rejected() -> None:
    store = RecordingConversationStore()

    with pytest.raises(ValueError, match="empty"):
        await AddTaskMessage(cast(TaskConversationStore, store)).execute(uuid.uuid4(), "  ")
