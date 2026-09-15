"""Operator queries and responses; no provider requests or model calls in HTTP handlers."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.agent_runtime.infrastructure.reservations import periodic_usage
from app.coordinator.infrastructure.inbox import human_response
from app.coordinator.infrastructure.models import CoordinatorAction, CoordinatorRun, HumanRequest
from app.coordinator.infrastructure.queries import latest_human_request
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.configuration.settings import Settings
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.team_models import Team


def human_view(row: HumanRequest) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "task_id": str(row.task_id),
        "question": row.question,
        "why_needed": row.reason,
        "choices": row.choices,
        "status": row.status,
        "answer": row.answer,
        "created_at": row.created_at.isoformat(),
    }


class CoordinationAdministration:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.sessions, self.settings = sessions, settings

    async def task(self, task_id: UUID) -> dict[str, Any]:
        async with self.sessions() as session:
            current_task = await session.get(Task, task_id)
            if current_task is None:
                raise LookupError("Task not found")
            runs = list(
                await session.scalars(
                    select(CoordinatorRun)
                    .where(CoordinatorRun.task_id == task_id)
                    .order_by(CoordinatorRun.created_at.desc())
                    .limit(20)
                )
            )
            actions = list(
                await session.scalars(
                    select(CoordinatorAction)
                    .where(CoordinatorAction.task_id == task_id)
                    .order_by(CoordinatorAction.created_at.desc())
                    .limit(20)
                )
            )
            action_key = TaskEvent.payload["action_id"].as_string()
            labels = (
                await session.execute(
                    select(
                        action_key,
                        TaskEvent.payload["verdict"].as_string(),
                    )
                    .where(
                        TaskEvent.task_id == task_id,
                        TaskEvent.event_type == "COORDINATOR_ACTION_REVIEWED",
                        TaskEvent.source == "dashboard",
                        action_key.in_([str(a.id) for a in actions]),
                    )
                    .distinct(action_key)
                    .order_by(action_key, TaskEvent.id.desc())
                )
            ).all()
            reviews: dict[str, str] = {key: value for key, value in labels}
            human = await session.scalar(
                latest_human_request(current_task).where(HumanRequest.status == "OPEN")
            )
            return {
                "mode": self.settings.coordinator_mode
                if "dashboard" in self.settings.coordinator_providers
                else "off",
                "human_request": human_view(human) if human else None,
                "runs": [
                    {
                        "id": str(r.id),
                        "status": r.status,
                        "mode": r.mode,
                        "decision": r.decision,
                        "error": r.error,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in runs
                ],
                "actions": [
                    {
                        "id": str(a.id),
                        "type": a.kind,
                        "review": reviews.get(str(a.id)),
                        "status": a.status,
                        "error": a.error,
                        "provider_effect_ref": a.provider_effect_ref,
                    }
                    for a in actions
                ],
            }

    async def review_action(self, task_id: UUID, action_id: UUID, verdict: str) -> None:
        if verdict not in {"CORRECT", "INCORRECT"}:
            raise ValueError("Choose a supported action assessment")
        async with self.sessions.begin() as session:
            action = await session.get(CoordinatorAction, action_id, with_for_update=True)
            if not action or action.task_id != task_id:
                raise LookupError("Task action not found")
            session.add(
                TaskEvent(
                    task_id=task_id,
                    source="dashboard",
                    event_type="COORDINATOR_ACTION_REVIEWED",
                    payload={"action_id": str(action_id), "verdict": verdict},
                )
            )

    async def reconcile(self, task_id: UUID, action_id: UUID) -> None:
        async with self.sessions.begin() as session:
            action = await session.get(CoordinatorAction, action_id, with_for_update=True)
            if not action or action.task_id != task_id:
                raise LookupError("Task action not found")
            if action.status != "UNKNOWN":
                raise ValueError("Only uncertain deliveries can be checked")
            if action.kind == "REQUEST_REVIEW":
                raise ValueError("Review requests require inspection of GitHub review history")
            action.arguments = {**action.arguments, "reconcile_requested": True}

    async def respond(self, task_id: UUID, request_id: UUID, answer: str) -> None:
        async with self.sessions.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            if not task:
                raise LookupError("Task not found")
            await human_response(session, task, request_id, answer)
            session.add(
                TaskMessage(
                    task_id=task_id,
                    author_type="USER",
                    author_name="You",
                    kind="COMMENT",
                    body=answer,
                    context={"human_request_id": str(request_id), "routing": "coordinator"},
                )
            )
            session.add(
                TaskEvent(
                    task_id=task_id,
                    source="dashboard",
                    event_type="HUMAN_INPUT_RESOLVED",
                    payload={"request_id": str(request_id)},
                )
            )

    async def priority(self, task_id: UUID, priority: int) -> None:
        async with self.sessions.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            if not task:
                raise LookupError("Task not found")
            if task.status in {"MERGED", "CANCELLED", "FAILED"}:
                raise ValueError("Terminal tasks cannot be reprioritized")
            previous, task.priority = task.priority, priority
            for job in await session.scalars(
                select(Job)
                .where(
                    Job.task_id == task_id, Job.state.in_([JobState.QUEUED, JobState.RETRY_WAIT])
                )
                .with_for_update()
            ):
                job.priority = priority
            session.add(
                TaskEvent(
                    task_id=task_id,
                    source="dashboard",
                    event_type="TASK_QUEUE_CHANGED",
                    payload={"previous_priority": previous, "priority": priority},
                )
            )

    async def queue(self, team_id: UUID | None = None, offset: int = 0) -> dict[str, Any]:
        async with self.sessions() as session:
            team = await session.get(Team, team_id) if team_id else None
            if team_id and team is None:
                raise LookupError("Team not found")
            conditions: list[ColumnElement[bool]] = [
                Task.archived_at.is_(None),
                Task.status.not_in(["MERGED", "CANCELLED", "FAILED"]),
            ]
            if team_id:
                conditions.append(Task.team_id == team_id)
            current_job = (
                select(Job.id)
                .where(
                    Job.task_id == Task.id,
                    Job.state.in_(
                        [JobState.QUEUED, JobState.RETRY_WAIT, JobState.CLAIMED, JobState.RUNNING]
                    ),
                )
                .order_by(
                    case((Job.state.in_([JobState.CLAIMED, JobState.RUNNING]), 0), else_=1),
                    Job.created_at.desc(),
                )
                .correlate(Task)
                .limit(1)
                .scalar_subquery()
            )
            query = (
                select(Task, Team.name, Job)
                .outerjoin(Team, Team.id == Task.team_id)
                .outerjoin(
                    Job,
                    Job.id == current_job,
                )
                .where(*conditions)
                .order_by(Task.priority, Task.created_at)
                .offset(offset)
                .limit(200)
            )
            rows = (await session.execute(query)).all()
            total = int(await session.scalar(select(func.count(Task.id)).where(*conditions)) or 0)
            active = int(
                await session.scalar(
                    select(func.count(Job.id))
                    .join(Task)
                    .where(
                        *([Task.team_id == team_id] if team_id else []),
                        Job.action.in_(["DEVELOPER_TURN", "THINKER_TURN", "INTERPRET_EVENT"]),
                        Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
                    )
                )
                or 0
            )
            humans = list(
                await session.scalars(
                    select(HumanRequest)
                    .join(Task)
                    .where(
                        *conditions,
                        HumanRequest.status == "OPEN",
                        HumanRequest.lifecycle_revision == Task.lifecycle_version,
                        HumanRequest.requirement_revision == Task.requirement_version,
                    )
                    .order_by(HumanRequest.created_at)
                    .limit(100)
                )
            )
            entries = []
            for task, team_name, job in rows:
                lane = (
                    "RUNNING"
                    if job and job.state in {JobState.CLAIMED, JobState.RUNNING}
                    else "QUEUED"
                    if job
                    else "NEEDS_YOU"
                    if task.status in {"WAITING_HUMAN", "PAUSED"}
                    else "WAITING_EXTERNAL"
                    if task.status == "WAITING_EXTERNAL"
                    else "BACKLOG"
                )
                entries.append(
                    {
                        "id": str(task.id),
                        "title": task.title,
                        "team": team_name,
                        "team_id": str(task.team_id) if task.team_id else None,
                        "priority": task.priority,
                        "lane": lane,
                        "stage": task.stage,
                        "wait_reason": task.wait_reason,
                    }
                )
            now = datetime.now(UTC)
            today, day_unknown = await periodic_usage(
                session, now.replace(hour=0, minute=0, second=0, microsecond=0), team_id
            )
            month, month_unknown = await periodic_usage(
                session, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), team_id
            )
            policy = await read_policy(session, team_id) if team_id else None
            completed = (
                await session.execute(
                    select(Task, Team.name)
                    .outerjoin(Team, Team.id == Task.team_id)
                    .where(
                        Task.archived_at.is_(None),
                        Task.status == "MERGED",
                        Task.completed_at >= now - timedelta(days=7),
                        *([Task.team_id == team_id] if team_id else []),
                    )
                    .order_by(Task.completed_at.desc(), Task.id)
                    .limit(20)
                )
            ).all()
            return {
                "spending": {
                    "today_usd": None if day_unknown else str(today),
                    "month_usd": None if month_unknown else str(month),
                    "monthly_limit_usd": str(policy.monthly_budget_usd)
                    if policy and policy.monthly_budget_usd
                    else str(self.settings.account_monthly_budget_usd)
                    if not team_id and self.settings.account_monthly_budget_usd
                    else None,
                    "daily_allowance_exceeded": bool(
                        policy and policy.daily_allowance_usd and today > policy.daily_allowance_usd
                    ),
                },
                "offset": offset,
                "developer_slots": {
                    "busy": active,
                    "capacity": team.max_concurrent_tasks
                    if team
                    else self.settings.global_developer_slots,
                },
                "mode": self.settings.coordinator_mode
                if "dashboard" in self.settings.coordinator_providers
                else "off",
                "entries": entries,
                "recently_completed": [
                    {
                        "id": str(t.id),
                        "title": t.title,
                        "team": name,
                        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                    }
                    for t, name in completed
                ],
                "total": total,
                "truncated": total > offset + len(entries),
                "human_requests": [human_view(h) for h in humans],
            }
