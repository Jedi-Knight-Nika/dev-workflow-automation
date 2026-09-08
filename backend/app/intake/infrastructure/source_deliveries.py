import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import ExternalTaskSnapshot, Integration, Task, WebhookDelivery
from app.engineering.infrastructure.enrollment import enroll
from app.intake.infrastructure.tracker_comments import tracker_comment


async def process_source_delivery(session: AsyncSession) -> bool:
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.provider.in_(["slack", "trello"]), WebhookDelivery.status == "RECEIVED"
        )
        .order_by(WebhookDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return False
    try:
        async with session.begin_nested():
            if delivery.provider == "trello":
                integration = await session.scalar(
                    select(Integration)
                    .where(Integration.provider_name == "trello")
                    .with_for_update()
                )
                if integration:
                    # Poller is the authoritative card reader; signed events only wake it.
                    integration.last_synced_at = None
                    action = delivery.payload.get("action") or {}
                    if isinstance(action, dict) and action.get("type") == "commentCard":
                        data, actor = action.get("data") or {}, action.get("memberCreator") or {}
                        card = data.get("card") or {}
                        snapshot = await session.scalar(
                            select(ExternalTaskSnapshot).where(
                                ExternalTaskSnapshot.provider == "trello",
                                ExternalTaskSnapshot.external_id == str(card.get("id") or ""),
                            )
                        )
                        task = await session.get(Task, snapshot.task_id) if snapshot else None
                        if task:
                            await tracker_comment(
                                session,
                                task,
                                "trello",
                                delivery.delivery_id,
                                {
                                    "actor_id": actor.get("id"),
                                    "author": actor.get("fullName"),
                                    "raw_text": data.get("text"),
                                },
                            )
                delivery.status = "PROCESSED"
            else:
                settings = get_settings()
                event = delivery.payload.get("event") or {}
                if not isinstance(event, dict):
                    raise ValueError("Slack event must be an object")
                route = settings.slack_team_routes.get(
                    f"{delivery.payload.get('team_id')}:{event.get('channel')}"
                )
                actor = str(event.get("user") or "")
                if (
                    not route
                    or not settings.new_fixed_lifecycle
                    or event.get("bot_id")
                    or event.get("subtype")
                    or event.get("type") not in {"message", "app_mention"}
                    or actor not in route.get("actor_ids", "").split(",")
                ):
                    delivery.status = "IGNORED"
                else:
                    text = str(event.get("text") or "").strip()
                    # Events API message/app-mention syntax; this is not an
                    # interactive Slack slash-command endpoint.
                    text = re.sub(r"^<@[A-Z0-9]+>\s*", "", text)
                    create = re.fullmatch(r"/?task\s+(.+)", text, re.DOTALL)
                    parent_id = (
                        f"{delivery.payload['team_id']}:{event['channel']}:{event.get('thread_ts')}"
                    )
                    parent = (
                        await session.scalar(
                            select(ExternalTaskSnapshot).where(
                                ExternalTaskSnapshot.provider == "slack",
                                ExternalTaskSnapshot.external_id == parent_id,
                            )
                        )
                        if event.get("thread_ts")
                        else None
                    )
                    if parent:
                        task = await session.get(Task, parent.task_id)
                        if task and str(task.team_id) == route["team_id"]:
                            await tracker_comment(
                                session,
                                task,
                                "slack",
                                delivery.delivery_id,
                                {"actor_id": actor, "author": actor, "raw_text": text},
                                routed_actor=True,
                            )
                        delivery.status = "PROCESSED"
                    elif create is None or not 1 <= len(create[1]) <= 16000:
                        delivery.status = "IGNORED"
                    else:
                        external_id = (
                            f"{delivery.payload['team_id']}:{event['channel']}:{event['ts']}"
                        )
                        existing = await session.scalar(
                            select(ExternalTaskSnapshot.id).where(
                                ExternalTaskSnapshot.provider == "slack",
                                ExternalTaskSnapshot.external_id == external_id,
                            )
                        )
                        if existing is None:
                            task = Task(
                                title=create[1].splitlines()[0][:500],
                                description=create[1],
                                team_id=UUID(route["team_id"]),
                                repository_id=UUID(route["repository_id"]),
                            )
                            session.add(task)
                            await session.flush()
                            await enroll(session, task, settings, actor=f"slack:{actor}")
                            session.add(
                                ExternalTaskSnapshot(
                                    task_id=task.id,
                                    provider="slack",
                                    external_id=external_id,
                                    identifier=f"SLACK-{delivery.delivery_id}",
                                    raw_payload={"event_id": delivery.delivery_id},
                                )
                            )
                        delivery.status = "PROCESSED"
        delivery.last_error = None
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        delivery.status, delivery.last_error = (
            "FAILED",
            f"Source configuration/input error: {type(exc).__name__}",
        )
    delivery.processed_at = datetime.now(UTC)
    delivery.attempts += 1
    await session.commit()
    return True
