import builtins
import uuid
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.infrastructure.task_models import Job, Task
from app.platform.scheduling.states import JobState
from app.platform.telemetry.usage_query import complete_sum, metered_runs
from app.teams.application.ports.team_management import (
    AssignTaskCommand,
    SaveTeamCommand,
    ShutdownTeamResult,
    TaskAssignmentView,
    TeamConflict,
    TeamNotFound,
    TeamView,
    WakeTeamResult,
)
from app.teams.domain.automation import AutomationPolicy
from app.teams.domain.profiles import default_profiles
from app.teams.infrastructure.automation import TeamAutomationPolicy, policy_payload
from app.teams.infrastructure.profiles import initialize_profiles
from app.teams.infrastructure.team_models import TaskAssignment, Team


class SqlAlchemyTeamManagementWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[TeamView]:
        teams = list(
            (
                await self._session.scalars(
                    select(Team).where(Team.archived_at.is_(None)).order_by(Team.name)
                )
            ).all()
        )
        return await self._views(teams)

    async def get(self, team_id: uuid.UUID) -> TeamView | None:
        team = await self._session.get(Team, team_id)
        if team is None or team.archived_at:
            return None
        return (await self._views([team]))[0]

    async def create(self, command: SaveTeamCommand) -> TeamView:
        self._validate(command)
        team = Team(
            name=command.name.strip(),
            description=command.description.strip(),
            enabled=command.enabled,
            max_concurrent_tasks=command.max_concurrent_tasks,
            repository_ids=[str(item) for item in command.repository_ids],
        )
        self._session.add(team)
        try:
            await self._session.flush()
            await initialize_profiles(self._session, team.id, default_profiles())
            self._session.add(
                TeamAutomationPolicy(
                    team_id=team.id, configuration=policy_payload(AutomationPolicy())
                )
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise TeamConflict("A team with this name already exists") from exc
        return (await self._views([team]))[0]

    async def update(self, team_id: uuid.UUID, command: SaveTeamCommand) -> TeamView:
        self._validate(command)
        team = await self._session.get(Team, team_id)
        if team is None or team.archived_at:
            raise TeamNotFound("Team not found")
        team.name = command.name.strip()
        team.description = command.description.strip()
        team.enabled = command.enabled
        team.max_concurrent_tasks = command.max_concurrent_tasks
        team.repository_ids = [str(item) for item in command.repository_ids]
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise TeamConflict("A team with this name already exists") from exc
        return (await self._views([team]))[0]

    async def archive(self, team_id: uuid.UUID) -> None:
        team = await self._session.get(Team, team_id)
        if team is None or team.archived_at:
            raise TeamNotFound("Team not found")
        running = await self._session.scalar(
            select(func.count())
            .select_from(Job)
            .join(Task)
            .where(Task.team_id == team_id, Job.state.in_([JobState.CLAIMED, JobState.RUNNING]))
        )
        if running:
            raise TeamConflict("Pause or finish running team tasks before archiving")
        team.enabled = False
        team.archived_at = datetime.now(UTC)
        await self._session.execute(
            update(TaskAssignment)
            .where(TaskAssignment.team_id == team_id, TaskAssignment.status == "QUEUED")
            .values(status="CANCELLED", completed_at=datetime.now(UTC))
        )
        await self._session.commit()

    async def assign(self, command: AssignTaskCommand) -> TaskAssignmentView:
        team = await self._session.get(Team, command.team_id)
        task = await self._session.get(Task, command.task_id, with_for_update=True)
        if team is None or team.archived_at or not team.enabled:
            raise TeamNotFound("Active team not found")
        if task is None:
            raise TeamNotFound("Task not found")
        active_jobs = await self._session.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.task_id == task.id,
                Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
            )
        )
        if task.workspace_path:
            raise TeamConflict("An enrolled task keeps its owning Team and native session")
        if active_jobs:
            raise TeamConflict("Cannot reassign a task while an agent is running")
        if (
            team.repository_ids
            and task.repository_id
            and str(task.repository_id) not in team.repository_ids
        ):
            raise TeamConflict("Task repository is not granted to this team")
        await self._session.execute(
            update(TaskAssignment)
            .where(
                TaskAssignment.task_id == task.id,
                TaskAssignment.status.in_(["QUEUED", "RUNNING"]),
            )
            .values(status="CANCELLED", completed_at=datetime.now(UTC))
        )
        position = (
            int(
                await self._session.scalar(
                    select(func.coalesce(func.max(TaskAssignment.queue_position), 0)).where(
                        TaskAssignment.team_id == team.id
                    )
                )
                or 0
            )
            + 1
        )
        assignment = TaskAssignment(
            task_id=task.id,
            team_id=team.id,
            status="QUEUED",
            queue_position=position,
            reason=command.reason,
        )
        task.team_id = team.id
        self._session.add(assignment)
        from app.engineering.infrastructure.job_queue import request_execution

        await self._session.flush()
        if command.start_work and task.status == "NEW":
            await request_execution(self._session, task, actor="user:team-assignment")
        await self._session.commit()
        await self._session.refresh(assignment)
        return self._assignment_view(assignment)

    async def unassign(self, task_id: uuid.UUID) -> None:
        task = await self._session.get(Task, task_id, with_for_update=True)
        if task is None:
            raise TeamNotFound("Task not found")
        active_jobs = await self._session.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.task_id == task.id,
                Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
            )
        )
        if task.workspace_path:
            raise TeamConflict("An enrolled task keeps its owning Team and native session")
        if active_jobs:
            raise TeamConflict("Cannot unassign a task while an agent is running")
        await self._session.execute(
            update(TaskAssignment)
            .where(
                TaskAssignment.task_id == task.id,
                TaskAssignment.status.in_(["QUEUED", "RUNNING"]),
            )
            .values(status="CANCELLED", completed_at=datetime.now(UTC))
        )
        await self._session.execute(
            update(Job)
            .where(Job.task_id == task.id, Job.state == JobState.QUEUED)
            .values(state=JobState.CANCELLED, finished_at=datetime.now(UTC))
        )
        task.team_id = None
        await self._session.commit()

    async def assignments(self, team_id: uuid.UUID) -> builtins.list[TaskAssignmentView]:
        records = list(
            (
                await self._session.scalars(
                    select(TaskAssignment)
                    .where(TaskAssignment.team_id == team_id)
                    .order_by(TaskAssignment.assigned_at.desc())
                    .limit(500)
                )
            ).all()
        )
        tasks = {
            task.id: task
            for task in await self._session.scalars(
                select(Task).where(Task.id.in_([item.task_id for item in records]))
            )
        }
        views = []
        for item in records:
            view = self._assignment_view(item)
            task = tasks.get(item.task_id)
            if task and task.team_id == team_id and item.status in {"QUEUED", "RUNNING"}:
                view = replace(view, status=task.status, started_at=task.started_at)
            views.append(view)
        return views

    async def wake(self, team_id: uuid.UUID) -> WakeTeamResult:
        from app.engineering.infrastructure.job_queue import request_execution

        team = await self._session.get(Team, team_id)
        if team is None or team.archived_at or not team.enabled:
            raise TeamNotFound("Active team not found")
        team.execution_paused = False
        tasks = await self._session.scalars(
            select(Task)
            .where(
                Task.team_id == team_id,
                Task.status == "NEW",
                Task.archived_at.is_(None),
                Task.workspace_path.is_(None),
                Task.manual_takeover.is_(False),
            )
            .order_by(Task.priority, Task.created_at)
            .with_for_update()
        )
        created = missing = 0
        for task in tasks:
            missing += int(task.repository_id is None)
            await request_execution(self._session, task, actor="user:team-wake")
            created += int(task.workspace_path is not None)
        await self._session.commit()
        counts = {
            state: count
            for state, count in (
                await self._session.execute(
                    select(Job.state, func.count())
                    .join(Task)
                    .where(Task.team_id == team_id)
                    .group_by(Job.state)
                )
            ).all()
        }
        return WakeTeamResult(
            0,
            created,
            counts.get(JobState.QUEUED, 0),
            counts.get(JobState.CLAIMED, 0) + counts.get(JobState.RUNNING, 0),
            missing,
        )

    async def shutdown(self, team_id: uuid.UUID) -> ShutdownTeamResult:
        from app.engineering.domain.lifecycle import Action
        from app.engineering.infrastructure.controls import control_task

        team = await self._session.get(Team, team_id)
        if team is None or team.archived_at:
            raise TeamNotFound("Team not found")
        team.execution_paused = True
        tasks = list(
            await self._session.scalars(
                select(Task)
                .where(
                    Task.team_id == team_id,
                    Task.status.in_(["NEW", "ACTIVE", "WAITING_EXTERNAL", "WAITING_HUMAN"]),
                    Task.archived_at.is_(None),
                )
                .order_by(Task.id)
                .with_for_update()
            )
        )
        count = 0
        for task in tasks:
            count += int(
                await self._session.scalar(
                    select(func.count(Job.id)).where(
                        Job.task_id == task.id,
                        Job.state.notin_([JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED]),
                    )
                )
                or 0
            )
            await control_task(self._session, task, Action.PAUSE, actor="user:team-shutdown")
        # Stop new claims as well as running tasks; wake never resets paused tickets or usage.
        await self._session.commit()
        return ShutdownTeamResult(count, len(tasks))

    async def _views(self, teams: builtins.list[Team]) -> builtins.list[TeamView]:
        if not teams:
            return []
        team_ids = [team.id for team in teams]
        count_rows = (
            await self._session.execute(
                select(
                    Task.team_id,
                    func.count().filter(Task.status == "NEW"),
                    func.count().filter(Task.status == "ACTIVE"),
                    func.count().filter(Task.status == "MERGED"),
                )
                .where(Task.team_id.in_(team_ids), Task.archived_at.is_(None))
                .group_by(Task.team_id)
            )
        ).all()
        counts = {row[0]: (int(row[1]), int(row[2]), int(row[3])) for row in count_rows}
        measured = metered_runs().c
        usage_rows = (
            await self._session.execute(
                select(
                    measured.team_id,
                    func.coalesce(func.sum(measured.input_tokens), 0),
                    func.coalesce(func.sum(measured.output_tokens), 0),
                    complete_sum(measured.cost_usd),
                )
                .where(measured.team_id.in_(team_ids))
                .group_by(measured.team_id)
            )
        ).all()
        usage = {
            row[0]: (int(row[1]), int(row[2]), float(row[3]) if row[3] is not None else None)
            for row in usage_rows
        }
        return [
            TeamView(
                team.id,
                team.name,
                team.description,
                team.enabled,
                team.max_concurrent_tasks,
                tuple(uuid.UUID(value) for value in team.repository_ids or []),
                *counts.get(team.id, (0, 0, 0)),
                *usage.get(team.id, (0, 0, 0.0)),
                team.created_at,
                team.updated_at,
                team.execution_paused,
            )
            for team in teams
        ]

    @staticmethod
    def _assignment_view(item: TaskAssignment) -> TaskAssignmentView:
        return TaskAssignmentView(
            item.id,
            item.task_id,
            item.team_id,
            item.status,
            item.queue_position,
            item.reason,
            item.assigned_at,
            item.started_at,
            item.completed_at,
        )

    @staticmethod
    def _validate(command: SaveTeamCommand) -> None:
        if not command.name.strip():
            raise ValueError("Team name cannot be blank")
        if not 1 <= command.max_concurrent_tasks <= 32:
            raise ValueError("Team concurrency must be between 1 and 32")
