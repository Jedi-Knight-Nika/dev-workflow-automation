import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.task_conversation import (
    TaskMessagePage,
    TaskMessageView,
)
from app.db.models import Task, TaskMessage
from app.infrastructure.persistence.job_operations import record_event


def _view(message: TaskMessage) -> TaskMessageView:
    return TaskMessageView(
        message.id,
        message.task_id,
        message.job_id,
        message.agent_id,
        message.author_type,
        message.author_name,
        message.author_role,
        message.kind,
        message.body,
        message.context,
        message.created_at,
    )


class SqlAlchemyTaskConversationStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_messages(
        self, task_id: uuid.UUID, limit: int, before_id: int | None
    ) -> TaskMessagePage:
        statement = select(TaskMessage).where(TaskMessage.task_id == task_id)
        if before_id is not None:
            statement = statement.where(TaskMessage.id < before_id)
        records = list(
            (
                await self._session.scalars(
                    statement.order_by(TaskMessage.id.desc()).limit(limit + 1)
                )
            ).all()
        )
        has_more = len(records) > limit
        visible = records[:limit]
        visible.reverse()
        return TaskMessagePage(
            [_view(record) for record in visible],
            visible[0].id if has_more and visible else None,
        )

    async def add_user_message(self, task_id: uuid.UUID, body: str) -> TaskMessageView:
        task = await self._session.get(Task, task_id)
        if task is None:
            raise LookupError("Task not found")
        message = TaskMessage(
            task_id=task_id,
            author_type="USER",
            author_name="You",
            kind="COMMENT",
            body=body,
            context={"task_state": task.state.value},
        )
        self._session.add(message)
        await self._session.flush()
        await record_event(
            self._session,
            task_id,
            "TASK_MESSAGE_ADDED",
            {"message_id": message.id, "author_type": "USER"},
        )
        await self._session.commit()
        return _view(message)
