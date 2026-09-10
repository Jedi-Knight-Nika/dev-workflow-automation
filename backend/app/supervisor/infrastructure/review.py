"""Review event wake of the same task Supervisor; no separate Interpreter agent."""

import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Task
from app.intake.domain.events import Event
from app.intake.infrastructure.metered import CloudInterpreter
from app.intake.infrastructure.ollama import classification_messages
from app.platform.configuration.settings import Settings
from app.supervisor.infrastructure.memory import task_memory
from app.supervisor.infrastructure.schemas import SYSTEM_POLICY


async def review_supervisor(
    sessions: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    settings: Settings,
    task: Task,
    event: Event,
) -> CloudInterpreter:
    latest = await session.scalar(
        select(AIRun)
        .where(AIRun.task_id == task.id, AIRun.role_kind == "DEVELOPER")
        .order_by(AIRun.started_at.desc())
        .limit(1)
    )
    validation = (
        await session.scalars(
            select(ValidationRun)
            .where(
                ValidationRun.task_id == task.id, ValidationRun.head_sha == task.current_revision
            )
            .limit(12)
        )
    ).all()
    packet = {
        "task_id": str(task.id),
        "objective": task.title + "\n" + task.description,
        "stage": task.stage,
        "current_sha": task.current_revision,
        "pr_number": task.pull_request_number,
        "memory": await task_memory(session, task.id),
        "developer_result": {"status": latest.status, "failure": latest.failure_code}
        if latest
        else None,
        "validation": [{"status": r.status, "exit_code": r.exit_code} for r in validation],
        "latest_event": {"body": event.body, "head_sha": event.head_sha},
    }
    body = json.dumps(packet, ensure_ascii=False)
    if len(body.encode()) > 22000:
        raise ValueError("Task Supervisor event packet exceeds bound")
    policy = classification_messages(event)[0]["content"]
    messages = [
        {
            "role": "system",
            "content": SYSTEM_POLICY
            + "\nOn a PR event, return the event decision JSON below instead of intake annotations. You are the same task Supervisor using your durable memory. Informal language and typos can express approval; do not confuse them with missing requirements. Never infer approval from past approval, checks alone, negation, conditions, or requests for more changes.\n"
            + policy,
        },
        {"role": "user", "content": body},
    ]
    return CloudInterpreter(
        sessions,
        task.id,
        "openai/" + settings.supervisor_model,
        Decimal(str(settings.supervisor_request_limit_usd)),
        settings.interpreter_timeout_seconds,
        role_kind="SUPERVISOR",
        messages=messages,
    )
