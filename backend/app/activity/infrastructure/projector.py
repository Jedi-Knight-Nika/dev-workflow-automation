"""Project committed business records; never acquire an engineering/task lock.

There is no high-water cursor over source IDs: concurrent transactions can commit
out of ID order. Indexed anti-joins find unseen records, including late commits.
The activity-only advisory lock serializes projection commits, making the public
sequence safe for replay snapshots and live catch-up across process replicas.
"""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, cast, exists, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import InstrumentedAttribute, load_only
from sqlalchemy.sql.elements import ColumnElement

from app.activity.domain.events import (
    Activity,
    amount,
    check_kind,
    identifier,
    reference,
    task_activity,
)
from app.activity.infrastructure.causality import attach_references
from app.activity.infrastructure.deployments import deployment_activities
from app.activity.infrastructure.models import ActivityEvent, ActivityProjectionState
from app.agent_runtime.domain.request_usage import public_request_count
from app.agent_runtime.infrastructure.models import AIRun
from app.coordinator.infrastructure.models import CoordinatorEvent
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.models import ReviewCycle, ValidationRun
from app.engineering.infrastructure.task_models import Job, TaskEvent
from app.intake.domain.ci import CI_KINDS

PROJECTION_LOCK = 781903141
PROJECTOR_VERSION = 4


def unseen(source: str, identity: ColumnElement[str]) -> ColumnElement[bool]:
    return ~exists().where(
        ActivityEvent.source_type == source,
        ActivityEvent.source_id == identity,
        ActivityEvent.projector_version >= PROJECTOR_VERSION,
    )


class ActivityProjector:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], batch_size: int = 100):
        self.sessions = sessions
        self.batch_size = batch_size

    async def project(self) -> int:
        async with self.sessions() as session, session.begin():
            if not await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": PROJECTION_LOCK}
            ):
                return 0
            activities: list[Activity] = []
            batches = [
                await self.task_events(session),
                await self.runs(session, finished=False),
                await self.runs(session, finished=True),
                await self.messages(session),
                await self.validations(session),
                await self.reviews(session),
                await self.jobs(session, finished=False),
                await self.jobs(session, finished=True),
                await self.coordination_events(session),
                await deployment_activities(session, self.batch_size, PROJECTOR_VERSION),
            ]
            for batch in batches:
                activities.extend(batch)
            activities = await attach_references(session, activities)
            if activities:
                values = []
                for activity in sorted(
                    activities,
                    key=lambda item: (item.occurred_at, item.source_type, item.source_id),
                ):
                    value = asdict(activity)
                    value["source_references"] = value.pop("references")
                    value["projector_version"] = PROJECTOR_VERSION
                    values.append(value)
                statement = insert(ActivityEvent).values(values)
                await session.execute(
                    statement.on_conflict_do_update(
                        constraint="uq_activity_source",
                        set_={
                            "kind": statement.excluded.kind,
                            "actor": statement.excluded.actor,
                            "actor_type": statement.excluded.actor_type,
                            "detail_level": statement.excluded.detail_level,
                            "payload": statement.excluded.payload,
                            "source_references": statement.excluded.source_references,
                            "projector_version": PROJECTOR_VERSION,
                        },
                    )
                )
            state = await session.get(ActivityProjectionState, 1)
            if state is None:
                state = ActivityProjectionState(id=1)
                session.add(state)
            state.last_success_at = datetime.now(UTC)
            state.caught_up = all(len(batch) < self.batch_size for batch in batches)
            return len(activities)

    async def task_events(self, session: AsyncSession) -> list[Activity]:
        rows = await session.scalars(
            select(TaskEvent)
            .where(unseen("task_event", cast(TaskEvent.id, String)))
            .order_by(TaskEvent.id)
            .limit(self.batch_size)
        )
        return [
            task_activity(
                r.id,
                r.task_id,
                r.event_type,
                r.payload if isinstance(r.payload, dict) else {},
                r.created_at,
                r.source,
            )
            for r in rows
        ]

    async def runs(self, session: AsyncSession, *, finished: bool) -> list[Activity]:
        suffix = ":finished" if finished else ":started"
        fields: tuple[InstrumentedAttribute[Any], ...] = (
            AIRun.id,
            AIRun.task_id,
            AIRun.role_kind,
            AIRun.provider,
            AIRun.model,
            AIRun.status,
            AIRun.started_at,
            AIRun.job_id,
        )
        if finished:
            fields += (
                AIRun.finished_at,
                AIRun.provider_cost_usd,
                AIRun.calculated_cost_usd,
                AIRun.raw_usage,
                AIRun.input_tokens,
                AIRun.output_tokens,
                AIRun.cache_read_tokens,
                AIRun.usage_complete,
            )
        query = (
            select(AIRun)
            .options(load_only(*fields, raiseload=True))
            .where(unseen("ai_run", cast(AIRun.id, String) + suffix))
        )
        if finished:
            query = query.where(AIRun.finished_at.is_not(None), AIRun.status != "RUNNING")
        rows = await session.scalars(
            query.order_by(AIRun.started_at, AIRun.id).limit(self.batch_size)
        )
        result = []
        for row in rows:
            facts: dict[str, Any] = {
                "run_id": str(row.id),
                "role": row.role_kind,
                "provider": row.provider[:40],
                "model": row.model[:120],
                "status": row.status if finished else "RUNNING",
                "job_id": str(row.job_id) if row.job_id else None,
            }
            if finished:
                cost = (
                    row.provider_cost_usd
                    if row.provider_cost_usd is not None
                    else row.calculated_cost_usd
                )
                # A later manual reconciliation has its own event; do not backdate it.
                if isinstance(row.raw_usage, dict) and row.raw_usage.get(
                    "operator_cost_reconciliation"
                ):
                    cost = None
                facts.update(
                    {
                        "cost_usd": amount(cost),
                        "input_tokens": row.input_tokens,
                        "output_tokens": row.output_tokens,
                        "cache_read_tokens": row.cache_read_tokens,
                        "usage_complete": row.usage_complete,
                        **public_request_count(row.raw_usage),
                    }
                )
            result.append(
                Activity(
                    "ai_run",
                    str(row.id) + suffix,
                    row.task_id,
                    "AI_RUN_COMPLETED" if finished else "AI_RUN_STARTED",
                    row.finished_at if finished and row.finished_at else row.started_at,
                    "agent",
                    row.role_kind.title()[:120],
                    2,
                    row.job_id,
                    facts,
                )
            )
        return result

    async def messages(self, session: AsyncSession) -> list[Activity]:
        rows = await session.scalars(
            select(TaskMessage)
            .options(
                load_only(
                    TaskMessage.id,
                    TaskMessage.task_id,
                    TaskMessage.author_type,
                    TaskMessage.author_name,
                    TaskMessage.created_at,
                    TaskMessage.job_id,
                    TaskMessage.reply_to_id,
                    TaskMessage.context,
                    raiseload=True,
                )
            )
            .where(unseen("message", cast(TaskMessage.id, String)))
            .order_by(TaskMessage.id)
            .limit(self.batch_size)
        )
        result = []
        for row in rows:
            human = row.author_type.lower() in {"user", "human", "engineer"}
            actor_type = "system" if row.author_type.lower() == "system" else "agent"
            context = row.context if isinstance(row.context, dict) else {}
            provider = context.get("provider")
            result.append(
                Activity(
                    "message",
                    str(row.id),
                    row.task_id,
                    "MESSAGE_RECEIVED" if human else "MESSAGE_SENT",
                    row.created_at,
                    "human" if human else actor_type,
                    row.author_name[:120],
                    2,
                    row.job_id,
                    {
                        "message_id": row.id,
                        "reply_to_id": row.reply_to_id,
                        **{
                            key: str(value)
                            for key in ("action_id", "human_request_id")
                            if (value := identifier(context.get(key)))
                        },
                        "provider": provider
                        if provider in ("github", "trello", "linear", "slack", "dashboard")
                        else None,
                    },
                )
            )
        return result

    async def validations(self, session: AsyncSession) -> list[Activity]:
        rows = await session.scalars(
            select(ValidationRun)
            .options(
                load_only(
                    ValidationRun.id,
                    ValidationRun.task_id,
                    ValidationRun.started_at,
                    ValidationRun.finished_at,
                    ValidationRun.status,
                    ValidationRun.exit_code,
                    ValidationRun.head_sha,
                    ValidationRun.command,
                    ValidationRun.requirement_version,
                    raiseload=True,
                )
            )
            .where(
                ValidationRun.finished_at.is_not(None),
                unseen("validation", cast(ValidationRun.id, String)),
            )
            .order_by(ValidationRun.started_at, ValidationRun.id)
            .limit(self.batch_size)
        )
        return [
            Activity(
                "validation",
                str(r.id),
                r.task_id,
                "VALIDATION_CHECK_COMPLETED",
                r.finished_at or r.started_at,
                "system",
                "Validator",
                2,
                payload={
                    "status": r.status,
                    "exit_code": r.exit_code,
                    "head_sha": r.head_sha,
                    "check_kind": check_kind(r.command),
                    "requirement_version": r.requirement_version,
                },
            )
            for r in rows
        ]

    async def jobs(self, session: AsyncSession, *, finished: bool) -> list[Activity]:
        milestone = Job.finished_at if finished else Job.started_at
        suffix = ":finished" if finished else ":started"
        rows = await session.execute(
            select(Job.id, Job.task_id, Job.created_at, milestone, Job.attempt, Job.action)
            .where(milestone.is_not(None), unseen("job", cast(Job.id, String) + suffix))
            .order_by(milestone, Job.id)
            .limit(self.batch_size)
        )
        return [
            Activity(
                "job",
                str(id) + suffix,
                task_id,
                "JOB_FINISHED" if finished else "JOB_STARTED",
                at,
                payload={
                    "job_id": str(id),
                    "queued_at": queued.isoformat(),
                    "attempt": attempt,
                    "action": action,
                },
                references=[reference("job", f"{id}:started", "completes")] if finished else [],
                detail_level=2,
            )
            for id, task_id, queued, at, attempt, action in rows
        ]

    async def coordination_events(self, session: AsyncSession) -> list[Activity]:
        rows = await session.execute(
            select(
                CoordinatorEvent.id,
                CoordinatorEvent.task_id,
                CoordinatorEvent.created_at,
                CoordinatorEvent.provider,
                CoordinatorEvent.context["review_cycle_id"].as_string(),
                CoordinatorEvent.context["human_request_id"].as_string(),
            )
            .where(unseen("coordination_event", cast(CoordinatorEvent.id, String)))
            .order_by(CoordinatorEvent.created_at, CoordinatorEvent.id)
            .limit(self.batch_size)
        )
        return [
            Activity(
                "coordination_event",
                str(id),
                task_id,
                "COORDINATION_INPUT_RECEIVED",
                at,
                "integration",
                provider.title()[:120],
                2,
                payload={
                    "provider": provider
                    if provider
                    in ("github", "slack", "trello", "linear", "dashboard", "engineering")
                    else "other",
                    **({"review_cycle_id": str(identifier(review))} if identifier(review) else {}),
                    **({"human_request_id": str(identifier(human))} if identifier(human) else {}),
                },
            )
            for id, task_id, at, provider, review, human in rows
        ]

    async def reviews(self, session: AsyncSession) -> list[Activity]:
        rows = await session.scalars(
            select(ReviewCycle)
            .options(
                load_only(
                    ReviewCycle.id,
                    ReviewCycle.task_id,
                    ReviewCycle.created_at,
                    ReviewCycle.actor,
                    ReviewCycle.decision,
                    ReviewCycle.head_sha,
                    ReviewCycle.external_event_id,
                    raiseload=True,
                )
            )
            .where(unseen("review", cast(ReviewCycle.id, String)))
            .order_by(ReviewCycle.created_at, ReviewCycle.id)
            .limit(self.batch_size)
        )
        result = []
        for r in rows:
            source_kind = (
                r.external_event_id.split(":")[1]
                if r.external_event_id.startswith("github:")
                else None
            )
            kind = (
                "CI_NOTIFICATION_RECEIVED"
                if source_kind in CI_KINDS
                else "GITHUB_NOTIFICATION_RECEIVED"
                if source_kind == "pull_request"
                else "REVIEW_RECEIVED"
            )
            result.append(
                Activity(
                    "review",
                    str(r.id),
                    r.task_id,
                    kind,
                    r.created_at,
                    "human" if kind == "REVIEW_RECEIVED" else "integration",
                    r.actor[:120] if kind == "REVIEW_RECEIVED" else "GitHub",
                    1,
                    payload={
                        "decision": r.decision,
                        "head_sha": r.head_sha,
                        **(
                            {"notification_id": str(r.id)}
                            if kind == "CI_NOTIFICATION_RECEIVED"
                            else {}
                        ),
                    },
                )
            )
        return result
