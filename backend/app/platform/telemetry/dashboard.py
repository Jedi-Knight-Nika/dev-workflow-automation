import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.domain.lifecycle import TaskStatus
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.integrations.models import Integration
from app.platform.scheduling.models import WorkerNode
from app.platform.scheduling.states import JobState
from app.platform.telemetry.ports.dashboard_queries import (
    ActiveWorkerView,
    ActivityEventView,
    DashboardSnapshot,
    HealthCheckView,
    QueueItemView,
    TeamActivityView,
    TimeBucketView,
    UsageBucketView,
)
from app.platform.telemetry.usage_query import complete_sum, metered_runs
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team

RUN_USAGE = metered_runs()

ACTIVE_TASK_STATES = (TaskStatus.ACTIVE,)
ACTIVE_JOB_STATES = (JobState.CLAIMED, JobState.RUNNING)
QUEUED_JOB_STATES = (JobState.QUEUED, JobState.RETRY_WAIT)


class SqlAlchemyDashboardQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def snapshot(self, period: str) -> DashboardSnapshot:
        now = datetime.now(UTC)
        start, days = self._period_start(period, now)
        active_workers = await self._active_workers()
        queue = await self._queue()
        queued_jobs, running_jobs = (
            await self._session.execute(
                select(
                    func.count(Job.id).filter(Job.state.in_(QUEUED_JOB_STATES)),
                    func.count(Job.id).filter(Job.state.in_(ACTIVE_JOB_STATES)),
                ).where(Job.state.in_((*QUEUED_JOB_STATES, *ACTIVE_JOB_STATES)))
            )
        ).one()
        teams = await self._teams(start)
        events = await self._events()
        role_usage = await self._usage(start, "role")
        provider_usage = await self._usage(start, "provider")
        team_usage = await self._usage(start, "team")
        throughput = await self._history(start, days, usage=False)
        token_history = await self._history(start, days, usage=True)
        health = await self._health(now)
        completed = await self._count_tasks((TaskStatus.MERGED,), start)
        failed = await self._count_tasks((TaskStatus.FAILED,), start)
        tokens, cost = await self._usage_total(start)
        system_status, score = self._system_health(health)
        return DashboardSnapshot(
            period=period,
            generated_at=now,
            system_status=system_status,
            health_score=score,
            active_tasks=await self._count_tasks(ACTIVE_TASK_STATES),
            queued_jobs=queued_jobs,
            ready_to_merge=int(
                await self._session.scalar(
                    select(func.count(Task.id)).where(
                        Task.status == "ACTIVE", Task.stage == "MERGING"
                    )
                )
                or 0
            ),
            needs_human=await self._count_tasks((TaskStatus.WAITING_HUMAN,)),
            completed=completed,
            failed=failed,
            tokens=tokens,
            estimated_cost=cost,
            autonomy_rate=None,
            active_worker=active_workers[0] if active_workers else None,
            active_workers=tuple(active_workers),
            running_jobs=int(running_jobs),
            queue=tuple(queue),
            teams=tuple(teams),
            recent_events=tuple(events),
            usage_by_role=tuple(role_usage),
            usage_by_provider=tuple(provider_usage),
            usage_by_team=tuple(team_usage),
            throughput=tuple(throughput),
            token_history=tuple(token_history),
            health=tuple(health),
        )

    @staticmethod
    def _period_start(period: str, now: datetime) -> tuple[datetime, int]:
        if period == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0), 1
        days = 7 if period == "7d" else 30
        return now - timedelta(days=days - 1), days

    async def _count_tasks(
        self, states: tuple[TaskStatus, ...], start: datetime | None = None
    ) -> int:
        statement = select(func.count(Task.id)).where(Task.status.in_(states))
        if start is not None:
            statement = statement.where(func.coalesce(Task.completed_at, Task.updated_at) >= start)
        return int(await self._session.scalar(statement) or 0)

    async def _active_workers(self) -> list[ActiveWorkerView]:
        active_ids = select(Job.id).where(Job.state.in_(ACTIVE_JOB_STATES))
        usage = (
            select(
                RUN_USAGE.c.job_id,
                func.sum(RUN_USAGE.c.input_tokens).label("input_tokens"),
                func.sum(RUN_USAGE.c.output_tokens).label("output_tokens"),
            )
            .where(RUN_USAGE.c.job_id.in_(active_ids))
            .group_by(RUN_USAGE.c.job_id)
            .subquery()
        )
        rows = await self._session.execute(
            select(Job, Task, Team, TeamAgentProfile, usage.c.input_tokens, usage.c.output_tokens)
            .join(Task, Task.id == Job.task_id)
            .outerjoin(Team, Team.id == Task.team_id)
            .outerjoin(
                TeamAgentProfile,
                (TeamAgentProfile.team_id == Task.team_id)
                & (TeamAgentProfile.role_kind == "DEVELOPER")
                & (Job.action == "DEVELOPER_TURN"),
            )
            .outerjoin(usage, usage.c.job_id == Job.id)
            .where(Job.state.in_(ACTIVE_JOB_STATES))
            .order_by(Job.started_at, Job.id)
            .limit(20)
        )
        return [
            ActiveWorkerView(
                str(job.id),
                str(task.id),
                task.external_key or task.title,
                str(team.id) if team else None,
                team.name if team else None,
                agent.display_name if agent else None,
                job.action,
                agent.provider if agent else None,
                agent.model if agent else None,
                job.started_at,
                int(input_tokens or 0),
                int(output_tokens or 0),
                job.action,
            )
            for job, task, team, agent, input_tokens, output_tokens in rows
        ]

    async def _queue(self) -> list[QueueItemView]:
        rows = (
            await self._session.execute(
                select(Job, Task, Team)
                .join(Task, Task.id == Job.task_id)
                .outerjoin(Team, Team.id == Task.team_id)
                .where(Job.state.in_(QUEUED_JOB_STATES))
                .order_by(Job.priority, Job.created_at)
                .limit(25)
            )
        ).all()
        return [
            QueueItemView(
                str(job.id),
                str(task.id),
                task.external_key or task.title,
                str(team.id) if team else None,
                team.name if team else None,
                job.action,
                job.action,
                job.priority,
                job.state.value,
                job.created_at,
            )
            for job, task, team in rows
        ]

    async def _teams(self, start: datetime) -> list[TeamActivityView]:
        teams = list(
            (
                await self._session.scalars(
                    select(Team).where(Team.archived_at.is_(None)).order_by(Team.name)
                )
            ).all()
        )
        active_rows = (
            await self._session.execute(
                select(Job, Task, TeamAgentProfile)
                .join(Task, Task.id == Job.task_id)
                .outerjoin(
                    TeamAgentProfile,
                    (TeamAgentProfile.team_id == Task.team_id)
                    & (TeamAgentProfile.role_kind == "DEVELOPER")
                    & (Job.action == "DEVELOPER_TURN"),
                )
                .where(Job.state.in_(ACTIVE_JOB_STATES), Task.team_id.is_not(None))
                .order_by(Task.team_id, Job.started_at)
            )
        ).all()
        active_by_team: dict[uuid.UUID, tuple[Job, Task, TeamAgentProfile | None]] = {}
        for job, task, agent in active_rows:
            if task.team_id is not None:
                active_by_team.setdefault(task.team_id, (job, task, agent))

        queued_rows = (
            await self._session.execute(
                select(Task.team_id, func.count(Job.id))
                .join(Job, Job.task_id == Task.id)
                .where(Task.team_id.is_not(None), Job.state.in_(QUEUED_JOB_STATES))
                .group_by(Task.team_id)
            )
        ).all()
        queued_by_team: dict[uuid.UUID, int] = {
            team_id: int(count) for team_id, count in queued_rows if team_id is not None
        }
        task_metrics = {
            team_id: (int(open_prs), int(ready), int(attention))
            for team_id, open_prs, ready, attention in (
                await self._session.execute(
                    select(
                        Task.team_id,
                        func.count(Task.id).filter(
                            Task.pull_request_number.is_not(None), Task.status != TaskStatus.MERGED
                        ),
                        func.count(Task.id).filter(
                            (Task.status == "ACTIVE") & (Task.stage == "MERGING")
                        ),
                        func.count(Task.id).filter(Task.status.in_((TaskStatus.WAITING_HUMAN,))),
                    )
                    .where(Task.team_id.is_not(None))
                    .group_by(Task.team_id)
                )
            ).all()
        }
        token_rows = (
            await self._session.execute(
                select(
                    Task.team_id,
                    func.coalesce(
                        func.sum(
                            func.coalesce(RUN_USAGE.c.input_tokens, 0)
                            + func.coalesce(RUN_USAGE.c.output_tokens, 0)
                        ),
                        0,
                    ),
                )
                .join(Task, Task.id == RUN_USAGE.c.task_id)
                .where(Task.team_id.is_not(None), RUN_USAGE.c.started_at >= start)
                .group_by(Task.team_id)
            )
        ).all()
        tokens_by_team: dict[uuid.UUID, int] = {
            team_id: int(tokens) for team_id, tokens in token_rows if team_id is not None
        }
        latest_state_rows = (
            await self._session.execute(
                select(Task.team_id, Task.status)
                .where(Task.team_id.is_not(None))
                .distinct(Task.team_id)
                .order_by(Task.team_id, Task.updated_at.desc())
            )
        ).all()
        latest_states: dict[uuid.UUID, str] = {
            team_id: state for team_id, state in latest_state_rows if team_id is not None
        }

        result: list[TeamActivityView] = []
        for team in teams:
            current = active_by_team.get(team.id)
            active, task, agent = current if current else (None, None, None)
            queued = int(queued_by_team.get(team.id, 0))
            open_prs, ready, attention = task_metrics.get(team.id, (0, 0, 0))
            tokens = int(tokens_by_team.get(team.id, 0))
            latest_task_state = latest_states.get(team.id)
            status = self._team_status(active is not None, attention > 0, queued, latest_task_state)
            result.append(
                TeamActivityView(
                    str(team.id),
                    team.name,
                    status,
                    str(task.id) if task else None,
                    (task.external_key or task.title) if task else None,
                    agent.display_name if agent else None,
                    active.action if active else None,
                    agent.provider if agent else None,
                    agent.model if agent else None,
                    queued,
                    open_prs,
                    ready,
                    tokens,
                )
            )
        return result

    async def _events(self) -> list[ActivityEventView]:
        rows = (
            await self._session.execute(
                select(TaskEvent, Task, Team)
                .select_from(TaskEvent)
                .join(Task, Task.id == TaskEvent.task_id)
                .outerjoin(Team, Team.id == Task.team_id)
                .order_by(TaskEvent.created_at.desc())
                .limit(40)
            )
        ).all()
        result = []
        for event, task, team in rows:
            summary = (
                event.payload.get("summary")
                or event.payload.get("message")
                or event.payload.get("state")
                or event.event_type.replace("_", " ").title()
            )
            severity = (
                "ERROR"
                if any(word in event.event_type for word in ("FAILED", "CRASHED"))
                else "WARNING"
                if task.status in (TaskStatus.WAITING_HUMAN,)
                else "INFO"
            )
            result.append(
                ActivityEventView(
                    str(event.id),
                    event.created_at,
                    str(team.id) if team else None,
                    team.name if team else None,
                    str(task.id),
                    task.external_key or task.title,
                    event.source,
                    severity,
                    event.event_type,
                    str(summary)[:300],
                )
            )
        return result

    async def _usage(self, start: datetime, dimension: str) -> list[UsageBucketView]:
        inputs = func.coalesce(func.sum(RUN_USAGE.c.input_tokens), 0)
        outputs = func.coalesce(func.sum(RUN_USAGE.c.output_tokens), 0)
        cost = complete_sum(RUN_USAGE.c.cost_usd)
        statement: Any
        if dimension == "role":
            statement = (
                select(RUN_USAGE.c.role, inputs, outputs, cost)
                .where(RUN_USAGE.c.started_at >= start)
                .group_by(RUN_USAGE.c.role)
            )
        elif dimension == "provider":
            statement = (
                select(RUN_USAGE.c.provider, inputs, outputs, cost)
                .where(RUN_USAGE.c.started_at >= start)
                .group_by(RUN_USAGE.c.provider)
            )
        else:
            statement = (
                select(Team.name, inputs, outputs, cost)
                .join(Task, Task.id == RUN_USAGE.c.task_id)
                .join(Team, Team.id == Task.team_id)
                .where(RUN_USAGE.c.started_at >= start)
                .group_by(Team.name)
            )
        rows = (await self._session.execute(statement.order_by((inputs + outputs).desc()))).all()
        return [
            UsageBucketView(
                str(row_key.value if hasattr(row_key, "value") else row_key),
                int(input_count),
                int(output_count),
                float(row_cost) if row_cost is not None else None,
            )
            for row_key, input_count, output_count, row_cost in rows
        ]

    async def _usage_total(self, start: datetime) -> tuple[int, float | None]:
        inputs, outputs, cost = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(RUN_USAGE.c.input_tokens), 0),
                    func.coalesce(func.sum(RUN_USAGE.c.output_tokens), 0),
                    complete_sum(RUN_USAGE.c.cost_usd),
                ).where(RUN_USAGE.c.started_at >= start)
            )
        ).one()
        return int(inputs) + int(outputs), float(cost) if cost is not None else None

    @staticmethod
    def _team_status(active: bool, needs_human: bool, queued: int, latest_state: str | None) -> str:
        if active:
            return "WORKING"
        if needs_human:
            return "NEEDS_HUMAN"
        if latest_state in (TaskStatus.WAITING_EXTERNAL,):
            return "WAITING_EXTERNAL"
        if latest_state == TaskStatus.FAILED:
            return "ERROR"
        if latest_state == TaskStatus.PAUSED:
            return "PAUSED"
        return "WORKING" if queued else "IDLE"

    async def _history(self, start: datetime, days: int, *, usage: bool) -> list[TimeBucketView]:
        first = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if usage:
            bucket = func.date_trunc("day", RUN_USAGE.c.started_at).label("bucket")
            rows = (
                await self._session.execute(
                    select(
                        bucket,
                        func.coalesce(func.sum(RUN_USAGE.c.input_tokens), 0),
                        func.coalesce(func.sum(RUN_USAGE.c.output_tokens), 0),
                    )
                    .where(RUN_USAGE.c.started_at >= first)
                    .group_by(bucket)
                )
            ).all()
            usage_values = {row[0].date(): (int(row[1]), int(row[2])) for row in rows}
            return [
                TimeBucketView(
                    day.date().isoformat(),
                    input_tokens=usage_values.get(day.date(), (0, 0))[0],
                    output_tokens=usage_values.get(day.date(), (0, 0))[1],
                )
                for offset in range(days)
                if (day := first + timedelta(days=offset))
            ]
        bucket = func.date_trunc("day", func.coalesce(Task.completed_at, Task.updated_at)).label(
            "bucket"
        )
        rows = (
            await self._session.execute(
                select(
                    bucket,
                    func.sum(case((Task.status == TaskStatus.MERGED, 1), else_=0)),
                    func.sum(case((Task.status == TaskStatus.FAILED, 1), else_=0)),
                    func.sum(case((Task.manual_takeover.is_(True), 1), else_=0)),
                )
                .where(func.coalesce(Task.completed_at, Task.updated_at) >= first)
                .group_by(bucket)
            )
        ).all()
        task_values = {
            row[0].date(): (int(row[1] or 0), int(row[2] or 0), int(row[3] or 0)) for row in rows
        }
        return [
            TimeBucketView(day.date().isoformat(), *task_values.get(day.date(), (0, 0, 0)))
            for offset in range(days)
            if (day := first + timedelta(days=offset))
        ]

    async def _health(self, now: datetime) -> list[HealthCheckView]:
        checks = [HealthCheckView("Database", "HEALTHY", "Connected", now)]
        integrations = list((await self._session.scalars(select(Integration))).all())
        for provider in ("github", "linear", "trello", "openai", "anthropic", "deepseek"):
            item = next((entry for entry in integrations if entry.provider_name == provider), None)
            status = (
                "HEALTHY"
                if item and item.status.value == "CONNECTED"
                else "DEGRADED"
                if item
                else "NOT_CONFIGURED"
            )
            checks.append(
                HealthCheckView(
                    provider.title(),
                    status,
                    item.last_error if item and item.last_error else status.replace("_", " "),
                    item.updated_at if status == "HEALTHY" and item else None,
                    item.updated_at if status == "DEGRADED" and item else None,
                )
            )
        online = int(
            await self._session.scalar(
                select(func.count(WorkerNode.id)).where(
                    WorkerNode.last_heartbeat >= now - timedelta(seconds=60)
                )
            )
            or 0
        )
        checks.append(
            HealthCheckView(
                "Workers",
                "HEALTHY" if online else "CRITICAL",
                f"{online} online",
                now if online else None,
                now if not online else None,
            )
        )
        return checks

    @staticmethod
    def _system_health(checks: list[HealthCheckView]) -> tuple[str, int]:
        configured = [item for item in checks if item.status != "NOT_CONFIGURED"]
        if any(item.status == "CRITICAL" for item in configured):
            return "CRITICAL", max(
                0,
                round(sum(item.status == "HEALTHY" for item in configured) / len(configured) * 100),
            )
        if any(item.status == "DEGRADED" for item in configured):
            return "DEGRADED", round(
                sum(item.status == "HEALTHY" for item in configured) / len(configured) * 100
            )
        return "HEALTHY", 100
