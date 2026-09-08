import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.models import DeveloperSession
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.lifecycle import record_transition
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.task_models import Task
from app.intake.domain.events import Event, Intent, classify


async def operator_message(session: AsyncSession, task: Task, message: TaskMessage) -> None:
    """Local UI notes are free; only explicit commands change execution.

    Operator authority is explicit. Acknowledging a note never starts inference.
    """
    event = Event(
        "dashboard",
        str(message.id),
        "comment",
        "local-operator",
        message.body,
        str(task.id),
        authenticated=True,
    )
    intent = classify(event)
    message.context = {**message.context, "routing": "note-only"}
    if message.body.strip() == f"/status {task.id}":
        session.add(
            TaskMessage(
                task_id=task.id,
                author_type="SYSTEM",
                author_name="Workflow",
                kind="UPDATE",
                body=f"{task.status} · {task.stage} · {task.wait_reason}. No AI call was made for this status response.",
                context={"reply_to": message.id},
            )
        )
        return
    if intent is None:
        return
    if intent.intent in {Intent.PAUSE, Intent.RESUME, Intent.CANCEL}:
        await control_task(
            session, task, Action(intent.intent.value), actor="user:conversation-command"
        )
        message.context = {**message.context, "routing": "command-applied"}
    elif intent.intent == Intent.FEEDBACK:
        match = re.fullmatch(r"/feedback\s+[A-Za-z0-9_-]+\s+(.+)", message.body.strip(), re.DOTALL)
        assert match
        delta = match[1]
        if len(delta) > 16000 or task.status in {"MERGED", "CANCELLED", "FAILED"}:
            raise ValueError("Feedback must be at most 16000 characters for a nonterminal task")
        native = await session.scalar(
            select(DeveloperSession)
            .where(DeveloperSession.task_id == task.id)
            .order_by(DeveloperSession.generation.desc())
            .limit(1)
            .with_for_update()
        )
        if native is None:
            raise ValueError("Enroll the task before sending execution feedback")
        if not native.native_session_id:
            request = f"{task.description}\n\nOperator clarification:\n{delta}".strip()
            if len(task.title) + len(request) > 24000:
                raise ValueError("Clarified initial task exceeds the bounded request size")
            task.description = request
        native.checkpoint = {**native.checkpoint, "next_feedback": delta}
        if task.status != "PAUSED":
            await control_task(session, task, Action.PAUSE, actor="user:feedback")
        await record_transition(
            session,
            task.id,
            Action.REVISE_REQUIREMENT,
            expected_version=task.lifecycle_version,
            actor="user:feedback",
        )
        message.context = {**message.context, "routing": "feedback-saved-resume-required"}
        session.add(
            TaskMessage(
                task_id=task.id,
                author_type="SYSTEM",
                author_name="Workflow",
                kind="UPDATE",
                body="Feedback saved for the same native session. Work is paused. Inspect any interrupted usage, then use Resume work. No planner or paid response was started.",
                context={"reply_to": message.id},
            )
        )
