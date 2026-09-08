"""Read operator-issued, job-scoped retry grants from the durable audit log.

No model output or job payload can issue a grant. Operators must separately record
an explicit user approval before enqueueing its named job in the same transaction.
"""

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, TaskEvent


def grant_limits(
    payload: dict[str, Any], job: Job, max_tokens: int, max_calls: int
) -> tuple[int, int] | None:
    if payload.get("job_id") != str(job.id) or payload.get("approved_by") != "user":
        return None
    baseline_tokens = payload.get("baseline_tokens")
    baseline_calls = payload.get("baseline_calls")
    tokens = payload.get("additional_tokens")
    calls = payload.get("additional_calls")
    if not all(type(value) is int for value in (baseline_tokens, baseline_calls, tokens, calls)):
        return None
    baseline_tokens, baseline_calls, tokens, calls = (
        cast(int, value) for value in (baseline_tokens, baseline_calls, tokens, calls)
    )
    if baseline_tokens < 0 or baseline_calls < 0:
        return None
    if not 0 < tokens <= min(max_tokens or 120_000, 120_000) or not 0 < calls <= max_calls:
        return None
    return baseline_tokens + tokens, baseline_calls + calls


async def approved_attempt_limits(
    session: AsyncSession, job: Job, max_tokens: int, max_calls: int
) -> tuple[int, int] | None:
    event = await session.scalar(
        select(TaskEvent)
        .where(
            TaskEvent.task_id == job.task_id,
            TaskEvent.source == "user",
            TaskEvent.event_type == "EXECUTION_ATTEMPT_BUDGET_GRANTED",
            TaskEvent.payload["job_id"].as_string() == str(job.id),
        )
        .order_by(TaskEvent.id.desc())
        .limit(1)
    )
    if not isinstance(event, TaskEvent):
        return None
    return grant_limits(event.payload, job, max_tokens, max_calls)
