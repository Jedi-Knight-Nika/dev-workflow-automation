import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.task_conversation import (
    TaskMessagePage,
    TaskMessageView,
)
from app.db.models import Job, JobRole, JobState, Task, TaskMessage
from app.infrastructure.persistence.job_operations import enqueue_job, record_event


def _view(message: TaskMessage) -> TaskMessageView:
    return TaskMessageView(
        message.id,
        message.task_id,
        message.job_id,
        message.reply_to_id,
        message.agent_id,
        message.author_type,
        message.author_name,
        message.author_role,
        message.kind,
        message.body,
        message.context,
        message.created_at,
        message.edited_at,
        message.deleted_at,
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
        if task.execution_version == 2:
            from app.intake.infrastructure.operator_messages import operator_message

            await operator_message(self._session, task, message)
            await self._session.commit()
            return _view(message)
        pending_response = await self._session.scalar(
            select(Job.id).where(
                Job.task_id == task_id,
                Job.action == "RESPOND_TO_MESSAGE",
                Job.state.in_([JobState.QUEUED, JobState.CLAIMED, JobState.RUNNING]),
            )
        )
        if pending_response is None and task.team_id is not None:
            await enqueue_job(
                self._session,
                task,
                JobRole.DELIVERER,
                "RESPOND_TO_MESSAGE",
                payload={
                    "message_id": message.id,
                    "reply_to_id": reply_to_id,
                    "conversation_only": True,
                },
                preserve_task_state=True,
            )
        await self._session.commit()
        return _view(message)

    async def edit_user_message(
        self, task_id: uuid.UUID, message_id: int, body: str
    ) -> TaskMessageView:
        message = await self._session.scalar(
            select(TaskMessage)
            .where(TaskMessage.id == message_id, TaskMessage.task_id == task_id)
            .with_for_update()
        )
        if message is None:
            raise LookupError("Message not found")
        if message.author_type != "USER" or message.deleted_at is not None:
            raise ValueError("Only your own active messages can be edited")
        message.body = body
        message.edited_at = datetime.now(UTC)
        await record_event(
            self._session,
            task_id,
            "TASK_MESSAGE_EDITED",
            {"message_id": message.id},
            source="user",
        )
        await self._session.commit()
        return _view(message)

    async def toggle_reaction(
        self, task_id: uuid.UUID, message_id: int, reaction: str
    ) -> TaskMessageView:
        message = await self._session.scalar(
            select(TaskMessage)
            .where(TaskMessage.id == message_id, TaskMessage.task_id == task_id)
            .with_for_update()
        )
        if message is None:
            raise LookupError("Message not found")
        reactions = [str(item) for item in message.context.get("user_reactions", [])]
        reactions = (
            [item for item in reactions if item != reaction]
            if reaction in reactions
            else [*reactions, reaction]
        )
        message.context = {**message.context, "user_reactions": reactions}
        await self._session.commit()
        return _view(message)

    async def delete_user_message(self, task_id: uuid.UUID, message_id: int) -> bool:
        message = await self._session.scalar(
            select(TaskMessage)
            .where(TaskMessage.id == message_id, TaskMessage.task_id == task_id)
            .with_for_update()
        )
        if message is None:
            return False
        if message.author_type != "USER":
            raise ValueError("Only your own messages can be deleted")
        message.body = "Message deleted"
        message.deleted_at = datetime.now(UTC)
        message.context = {
            key: value for key, value in message.context.items() if key != "user_reactions"
        }
        await self._session.commit()
        return True
