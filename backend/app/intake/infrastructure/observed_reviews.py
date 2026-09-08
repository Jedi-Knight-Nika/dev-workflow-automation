"""Deduplicate authoritative GitHub message snapshots before interpretation."""

import hashlib
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.domain.review import ReviewedMessage, ReviewMessage
from app.engineering.infrastructure.models import ReviewCycle
from app.engineering.infrastructure.task_models import Task


async def observe_review_messages(
    session: AsyncSession, task: Task, messages: tuple[ReviewMessage, ...]
) -> None:
    for message in messages:
        identity = f"{message.key}:{message.head_sha}:{message.updated_at}:{message.digest}"
        event_id = "github:message:" + hashlib.sha256(identity.encode()).hexdigest()
        exists = await session.scalar(
            select(ReviewCycle.id).where(
                ReviewCycle.task_id == task.id, ReviewCycle.external_event_id == event_id
            )
        )
        if exists:
            continue
        snapshot = asdict(
            ReviewedMessage(
                message.key,
                message.actor_id,
                message.head_sha,
                message.digest,
                message.updated_at,
                "",
            )
        )
        snapshot.pop("decision")
        session.add(
            ReviewCycle(
                task_id=task.id,
                external_event_id=event_id,
                head_sha=message.head_sha,
                actor=message.actor_id,
                decision="CLASSIFY_PENDING" if len(message.body) <= 12000 else "TOO_LARGE",
                feedback={
                    "provider": "github",
                    "actor_type": "User",
                    "body": message.body[:16000],
                    "review_message": snapshot,
                },
            )
        )
    await session.flush()
