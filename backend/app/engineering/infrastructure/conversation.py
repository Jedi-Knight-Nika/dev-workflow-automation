import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.application.ports.task_conversation import (
    TaskMessagePage,
    TaskMessageView,
)
from app.engineering.infrastructure.job_queue import record_event
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.task_models import Task


def _view(message: TaskMessage) -> TaskMessageView:
    return TaskMessageView(
        message.id,
        message.task_id,
        message.job_id,
        message.reply_to_id,
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

    async def add_user_message(
        self, task_id: uuid.UUID, body: str, reply_to_id: int | None
    ) -> TaskMessageView:
        task = await self._session.get(Task, task_id, with_for_update=True)
        if task is None:
            raise LookupError("Task not found")
        if reply_to_id is not None:
            parent = await self._session.get(TaskMessage, reply_to_id)
            if parent is None or parent.task_id != task_id:
                raise ValueError("Reply target does not belong to this task")
        message = TaskMessage(
            task_id=task_id,
            reply_to_id=reply_to_id,
            author_type="USER",
            author_name="You",
            kind="COMMENT",
            body=body,
            context={"task_state": task.status},
        )
        self._session.add(message)
        await self._session.flush()
        await record_event(
            self._session,
            task_id,
            "TASK_MESSAGE_ADDED",
            {"message_id": message.id, "author_type": "USER"},
        )
        from app.intake.infrastructure.operator_messages import operator_message

        await operator_message(self._session, task, message)
        await self._session.commit()
        return _view(message)
