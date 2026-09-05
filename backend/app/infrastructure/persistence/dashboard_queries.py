from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.dashboard_queries import (
    ActiveWorkerView,
    ActivityEventView,
    DashboardSnapshot,
    HealthCheckView,
    QueueItemView,
    TeamActivityView,
    TimeBucketView,
    UsageBucketView,
)
from app.db.models import (
    AIAgent,
    Integration,
    Job,
    JobState,
    Repository,
    Task,
    TaskEvent,
    TaskState,
    Team,
    WorkerNode,
    WorkerRun,
    WorkflowDefinition,
    WorkflowNode,
)

ACTIVE_TASK_STATES = (
    TaskState.PLANNING,
    TaskState.QUEUED_FOR_EXECUTION,
    TaskState.IMPLEMENTING,
    TaskState.LOCAL_VALIDATION,
    TaskState.INTERNAL_REVIEW,
)
ACTIVE_JOB_STATES = (JobState.CLAIMED, JobState.RUNNING)
QUEUED_JOB_STATES = (JobState.QUEUED, JobState.RETRY_WAIT)


class SqlAlchemyDashboardQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def snapshot(self, period: str) -> DashboardSnapshot:
        now = datetime.now(UTC)
        start, days = self._period_start(period, now)
        active_job = await self._session.scalar(
            select(Job).where(Job.state.in_(ACTIVE_JOB_STATES)).order_by(Job.started_at).limit(1)
        )
        active_worker = await self._active_worker(active_job)
        queue = await self._queue()
        queued_jobs = int(
            await self._session.scalar(
                select(func.count(Job.id)).where(Job.state.in_(QUEUED_JOB_STATES))
            )
            or 0
        )
        teams = await self._teams(start)
        events = await self._events()
        role_usage = await self._usage(start, "role")
        provider_usage = await self._usage(start, "provider")
        team_usage = await self._usage(start, "team")
        throughput = await self._history(start, days, usage=False)
        token_history = await self._history(start, days, usage=True)
        health = await self._health(now)
        completed = await self._count_tasks((TaskState.MERGED,), start)
        failed = await self._count_tasks((TaskState.FAILED,), start)
        human_completed = int(
            await self._session.scalar(
                select(func.count(Task.id)).where(
                    Task.state == TaskState.MERGED,
                    Task.completed_at >= start,
                    Task.manual_takeover.is_(True),
                )
            )
            or 0
        )
        tokens, cost = await self._usage_total(start)
        system_status, score = self._system_health(health)
        return DashboardSnapshot(
            period=period,
            generated_at=now,
            system_status=system_status,
            health_score=score,
            active_tasks=await self._count_tasks(ACTIVE_TASK_STATES),
            queued_jobs=queued_jobs,
            ready_to_merge=await self._count_tasks((TaskState.READY_TO_MERGE,)),
            needs_human=await self._count_tasks((TaskState.NEEDS_HUMAN, TaskState.CONTEXT_PENDING)),
            completed=completed,
            failed=failed,
            tokens=tokens,
            estimated_cost=cost,
            autonomy_rate=round((completed - human_completed) / completed * 100, 1)
            if completed
            else None,
            active_worker=active_worker,
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
        self, states: tuple[TaskState, ...], start: datetime | None = None
    ) -> int:
        statement = select(func.count(Task.id)).where(Task.state.in_(states))
        if start is not None:
            statement = statement.where(Task.updated_at >= start)
        return int(await self._session.scalar(statement) or 0)

    async def _active_worker(self, job: Job | None) -> ActiveWorkerView | None:
        if job is None:
            return None
        task = await self._session.get(Task, job.task_id)
        if task is None:
            return None
        team = await self._session.get(Team, task.team_id) if task.team_id else None
        agent = None
        if task.team_id:
            agent = await self._session.scalar(
                select(AIAgent)
                .join(WorkflowNode, WorkflowNode.agent_id == AIAgent.id)
                .join(WorkflowDefinition, WorkflowDefinition.id == WorkflowNode.workflow_id)
                .where(
                    WorkflowDefinition.team_id == task.team_id, WorkflowNode.role == job.role.value
                )
                .limit(1)
            )
        usage = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(WorkerRun.input_tokens), 0),
                    func.coalesce(func.sum(WorkerRun.output_tokens), 0),
                ).where(WorkerRun.job_id == job.id)
            )
        ).one()
        return ActiveWorkerView(
            str(job.id),
            str(task.id),
            task.external_key or task.title,
            str(team.id) if team else None,
            team.name if team else None,
            agent.name if agent else None,
            job.role.value,
            agent.provider if agent else None,
            agent.model if agent else None,
            job.started_at,
            int(usage[0]),
            int(usage[1]),
        )

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
                job.role.value,
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
        result: list[TeamActivityView] = []
        for team in teams:
            active = await self._session.scalar(
                select(Job)
                .join(Task)
                .where(Task.team_id == team.id, Job.state.in_(ACTIVE_JOB_STATES))
                .order_by(Job.started_at)
                .limit(1)
            )
            task = await self._session.get(Task, active.task_id) if active else None
            agent = (
                await self._session.scalar(
                    select(AIAgent)
                    .join(WorkflowNode, WorkflowNode.agent_id == AIAgent.id)
                    .join(WorkflowDefinition, WorkflowDefinition.id == WorkflowNode.workflow_id)
                    .where(
                        WorkflowDefinition.team_id == team.id,
                        WorkflowNode.role == active.role.value,
                    )
                    .limit(1)
                )
                if active
                else None
            )
            queued = int(
                await self._session.scalar(
                    select(func.count(Job.id))
                    .join(Task)
                    .where(Task.team_id == team.id, Job.state.in_(QUEUED_JOB_STATES))
                )
                or 0
            )
            open_prs = int(
                await self._session.scalar(
                    select(func.count(Task.id)).where(
                        Task.team_id == team.id,
                        Task.pull_request_number.is_not(None),
                        Task.state != TaskState.MERGED,
                    )
                )
                or 0
            )
            ready = int(
                await self._session.scalar(
                    select(func.count(Task.id)).where(
                        Task.team_id == team.id, Task.state == TaskState.READY_TO_MERGE
                    )
                )
                or 0
            )
            tokens = int(
                await self._session.scalar(
                    select(
                        func.coalesce(
                            func.sum(
                                func.coalesce(WorkerRun.input_tokens, 0)
                                + func.coalesce(WorkerRun.output_tokens, 0)
                            ),
                            0,
                        )
                    )
                    .join(Job)
                    .join(Task)
                    .where(Task.team_id == team.id, WorkerRun.created_at >= start)
                )
                or 0
            )
            attention = await self._session.scalar(
                select(func.count(Task.id)).where(
                    Task.team_id == team.id,
                    Task.state.in_((TaskState.NEEDS_HUMAN, TaskState.CONTEXT_PENDING)),
                )
            )
            latest_task_state = await self._session.scalar(
                select(Task.state)
                .where(Task.team_id == team.id)
                .order_by(Task.updated_at.desc())
                .limit(1)
            )
            status = self._team_status(
                active is not None, bool(attention), queued, latest_task_state
            )
            result.append(
                TeamActivityView(
                    str(team.id),
                    team.name,
                    status,
                    str(task.id) if task else None,
                    (task.external_key or task.title) if task else None,
                    agent.name if agent else None,
                    active.role.value if active else None,
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
                if task.state in (TaskState.NEEDS_HUMAN, TaskState.CONTEXT_PENDING)
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
        inputs = func.coalesce(func.sum(WorkerRun.input_tokens), 0)
        outputs = func.coalesce(func.sum(WorkerRun.output_tokens), 0)
        cost = func.sum(WorkerRun.estimated_cost_usd)
        statement: Any
        if dimension == "role":
            statement = (
                select(WorkerRun.role, inputs, outputs, cost)
                .where(WorkerRun.created_at >= start)
                .group_by(WorkerRun.role)
            )
        elif dimension == "provider":
            statement = (
                select(WorkerRun.provider, inputs, outputs, cost)
                .where(WorkerRun.created_at >= start)
                .group_by(WorkerRun.provider)
            )
        else:
            statement = (
                select(Team.name, inputs, outputs, cost)
                .join(Job)
                .join(Task)
                .join(Team, Team.id == Task.team_id)
                .where(WorkerRun.created_at >= start)
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
                    func.coalesce(func.sum(WorkerRun.input_tokens), 0),
                    func.coalesce(func.sum(WorkerRun.output_tokens), 0),
                    func.sum(WorkerRun.estimated_cost_usd),
                ).where(WorkerRun.created_at >= start)
            )
        ).one()
        return int(inputs) + int(outputs), float(cost) if cost is not None else None

    @staticmethod
    def _team_status(
        active: bool, needs_human: bool, queued: int, latest_state: TaskState | None
    ) -> str:
        if active:
            return "WORKING"
        if needs_human:
            return "NEEDS_HUMAN"
        if latest_state in (TaskState.WAITING_GITHUB, TaskState.READY_TO_MERGE):
            return "WAITING_EXTERNAL"
        if latest_state == TaskState.FAILED:
            return "ERROR"
        if latest_state == TaskState.PAUSED:
            return "PAUSED"
        return "WORKING" if queued else "IDLE"

    async def _history(self, start: datetime, days: int, *, usage: bool) -> list[TimeBucketView]:
        result: list[TimeBucketView] = []
        first = start.replace(hour=0, minute=0, second=0, microsecond=0)
        for offset in range(days):
            day, end = first + timedelta(days=offset), first + timedelta(days=offset + 1)
            if usage:
                inputs, outputs = (
                    await self._session.execute(
                        select(
                            func.coalesce(func.sum(WorkerRun.input_tokens), 0),
                            func.coalesce(func.sum(WorkerRun.output_tokens), 0),
                        ).where(WorkerRun.created_at >= day, WorkerRun.created_at < end)
                    )
                ).one()
                result.append(
                    TimeBucketView(
                        day.date().isoformat(), input_tokens=int(inputs), output_tokens=int(outputs)
                    )
                )
            else:
                completed, failed, human = (
                    await self._session.execute(
                        select(
                            func.sum(case((Task.state == TaskState.MERGED, 1), else_=0)),
                            func.sum(case((Task.state == TaskState.FAILED, 1), else_=0)),
                            func.sum(case((Task.manual_takeover.is_(True), 1), else_=0)),
                        ).where(Task.updated_at >= day, Task.updated_at < end)
                    )
                ).one()
                result.append(
                    TimeBucketView(
                        day.date().isoformat(),
                        int(completed or 0),
                        int(failed or 0),
                        int(human or 0),
                    )
                )
        return result

    async def _health(self, now: datetime) -> list[HealthCheckView]:
        checks = [HealthCheckView("Database", "HEALTHY", "Connected", now)]
        integrations = list((await self._session.scalars(select(Integration))).all())
        for provider in ("github", "linear", "openai", "anthropic", "google"):
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
        repositories = list(
            (
                await self._session.scalars(select(Repository).where(Repository.enabled.is_(True)))
            ).all()
        )
        failed = sum(repo.index_status.value == "FAILED" for repo in repositories)
        stale = sum(
            bool(repo.latest_sha and repo.latest_sha != repo.indexed_sha) for repo in repositories
        )
        ready = sum(
            repo.index_status.value == "READY"
            and (not repo.latest_sha or repo.latest_sha == repo.indexed_sha)
            for repo in repositories
        )
        incomplete = len(repositories) - ready - failed
        rag_status = "DEGRADED" if failed or stale or incomplete else "HEALTHY"
        checks.append(
            HealthCheckView(
                "RAG",
                rag_status,
                f"{ready} ready · {stale} stale · {failed} failed · {incomplete} preparing",
                now if rag_status == "HEALTHY" else None,
                now if rag_status != "HEALTHY" else None,
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
