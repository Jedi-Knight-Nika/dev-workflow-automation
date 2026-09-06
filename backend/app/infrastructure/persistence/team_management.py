import builtins
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.team_management import (
    AssignTaskCommand,
    SaveTeamCommand,
    TaskAssignmentView,
    TeamConflict,
    TeamNotFound,
    TeamView,
    WakeTeamResult,
)
from app.db.models import Job, JobRole, JobState, Repository, Task, TaskAssignment, Team, WorkerRun
from app.infrastructure.persistence.workflow_designer import SqlAlchemyWorkflowDesigner


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
            await SqlAlchemyWorkflowDesigner(self._session, team.id).get()
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
            .select_from(TaskAssignment)
            .where(TaskAssignment.team_id == team_id, TaskAssignment.status == "RUNNING")
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
        task = await self._session.get(Task, command.task_id)
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
        queued_job = await self._session.scalar(
            select(Job.id).where(
                Job.task_id == task.id,
                Job.state.in_([JobState.QUEUED, JobState.CLAIMED, JobState.RUNNING]),
            )
        )
        if queued_job is None:
            self._session.add(
                Job(
                    task_id=task.id,
                    role=JobRole.INTAKE,
                    action="INTERPRET_TASK",
                    priority=task.priority,
                    payload={"source": "manual_team_assignment"},
                )
            )
        await self._session.commit()
        await self._session.refresh(assignment)
        return self._assignment_view(assignment)

    async def unassign(self, task_id: uuid.UUID) -> None:
        task = await self._session.get(Task, task_id)
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
        return [self._assignment_view(item) for item in records]

    async def wake(self, team_id: uuid.UUID) -> WakeTeamResult:
        team = await self._session.get(Team, team_id, with_for_update=True)
        if team is None or team.archived_at or not team.enabled:
            raise TeamNotFound("Active team not found")

        now = datetime.now(UTC)
        expired_job_ids = list(
            (
                await self._session.scalars(
                    select(Job.id)
                    .join(Task, Task.id == Job.task_id)
                    .where(
                        Task.team_id == team_id,
                        Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
                        Job.lease_expires_at.is_not(None),
                        Job.lease_expires_at < now,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        if expired_job_ids:
            await self._session.execute(
                update(Job)
                .where(Job.id.in_(expired_job_ids))
                .values(
                    state=JobState.QUEUED,
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    retry_not_before=None,
                    started_at=None,
                )
            )

        assignments = list(
            (
                await self._session.execute(
                    select(TaskAssignment, Task)
                    .join(Task, Task.id == TaskAssignment.task_id)
                    .where(
                        TaskAssignment.team_id == team_id,
                        TaskAssignment.status.in_(["QUEUED", "RUNNING"]),
                        Task.archived_at.is_(None),
                    )
                    .with_for_update()
                )
            ).all()
        )
        candidate_statement = (
            select(func.count())
            .select_from(Repository)
            .where(Repository.enabled.is_(True), Repository.archived_at.is_(None))
        )
        if team.repository_ids:
            candidate_statement = candidate_statement.where(
                Repository.id.in_([uuid.UUID(value) for value in team.repository_ids])
            )
        candidate_repository_count = int(await self._session.scalar(candidate_statement) or 0)
        active_task_ids = {
            task_id
            for task_id in (
                await self._session.scalars(
                    select(Job.task_id)
                    .join(Task, Task.id == Job.task_id)
                    .where(
                        Task.team_id == team_id,
                        Job.state.in_(
                            [
                                JobState.QUEUED,
                                JobState.CLAIMED,
                                JobState.RUNNING,
                                JobState.RETRY_WAIT,
                                JobState.WAITING_PROVIDER,
                                JobState.WAITING_INTEGRATION,
                                JobState.WAITING_CONFIGURATION,
                                JobState.WAITING_HUMAN,
                            ]
                        ),
                    )
                )
            ).all()
        }
        created_jobs = 0
        missing_repository_tasks = 0
        for assignment, task in assignments:
            if task.repository_id is None and candidate_repository_count == 0:
                missing_repository_tasks += 1
            if task.id in active_task_ids:
                continue
            self._session.add(
                Job(
                    task_id=task.id,
                    role=JobRole.INTAKE,
                    action="INTERPRET_TASK",
                    priority=task.priority,
                    payload={"source": "team_wake"},
                )
            )
            assignment.status = "QUEUED"
            assignment.started_at = None
            created_jobs += 1

        if expired_job_ids:
            expired_task_ids = set(
                (
                    await self._session.scalars(
                        select(Job.task_id).where(Job.id.in_(expired_job_ids))
                    )
                ).all()
            )
            for assignment, task in assignments:
                if task.id in expired_task_ids:
                    assignment.status = "QUEUED"
                    assignment.started_at = None

        await self._session.commit()
        queued_jobs = int(
            await self._session.scalar(
                select(func.count())
                .select_from(Job)
                .join(Task, Task.id == Job.task_id)
                .where(Task.team_id == team_id, Job.state == JobState.QUEUED)
            )
            or 0
        )
        running_jobs = int(
            await self._session.scalar(
                select(func.count())
                .select_from(Job)
                .join(Task, Task.id == Job.task_id)
                .where(Task.team_id == team_id, Job.state.in_([JobState.CLAIMED, JobState.RUNNING]))
            )
            or 0
        )
        return WakeTeamResult(
            recovered_jobs=len(expired_job_ids),
            created_jobs=created_jobs,
            queued_jobs=queued_jobs,
            running_jobs=running_jobs,
            missing_repository_tasks=missing_repository_tasks,
        )

    async def _views(self, teams: builtins.list[Team]) -> builtins.list[TeamView]:
        if not teams:
            return []
        team_ids = [team.id for team in teams]
        count_rows = (
            await self._session.execute(
                select(
                    TaskAssignment.team_id,
                    func.count().filter(TaskAssignment.status == "QUEUED"),
                    func.count().filter(TaskAssignment.status == "RUNNING"),
                    func.count().filter(TaskAssignment.status == "COMPLETED"),
                )
                .where(TaskAssignment.team_id.in_(team_ids))
                .group_by(TaskAssignment.team_id)
            )
        ).all()
        counts = {row[0]: (int(row[1]), int(row[2]), int(row[3])) for row in count_rows}
        usage_rows = (
            await self._session.execute(
                select(
                    Task.team_id,
                    func.coalesce(func.sum(WorkerRun.input_tokens), 0),
                    func.coalesce(func.sum(WorkerRun.output_tokens), 0),
                    func.coalesce(func.sum(WorkerRun.estimated_cost_usd), 0),
                )
                .join(Job, Job.task_id == Task.id)
                .join(WorkerRun, WorkerRun.job_id == Job.id)
                .where(Task.team_id.in_(team_ids))
                .group_by(Task.team_id)
            )
        ).all()
        usage = {row[0]: (int(row[1]), int(row[2]), float(row[3])) for row in usage_rows}
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
