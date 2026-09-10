"""Enrollment is explicit and transactional; it never rewrites old usage or source."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.models import DeveloperSession
from app.agent_runtime.infrastructure.versions import HARNESS_VERSIONS
from app.delivery.infrastructure.status_sync import enqueue_status
from app.engineering.infrastructure.jobs import enqueue_phase
from app.engineering.infrastructure.models import TaskPhaseRun
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.intake.domain.events import requirement_fingerprint
from app.platform.configuration.settings import Settings
from app.platform.scheduling.states import JobState
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


async def enroll(session: AsyncSession, task: Task, settings: Settings, *, actor: str) -> None:
    if await session.scalar(select(DeveloperSession.id).where(DeveloperSession.task_id == task.id)):
        return
    if task.team_id is None or task.repository_id is None:
        raise ValueError("A task needs a Team and unambiguous repository")
    team = await session.get(Team, task.team_id)
    repository = await session.get(Repository, task.repository_id)
    policy = await read_policy(session, task.team_id)
    if (
        not team
        or not team.enabled
        or team.execution_paused
        or team.archived_at
        or not repository
        or not repository.enabled
        or repository.archived_at
    ):
        raise ValueError("Team and repository must be available")
    if not policy.enrollment_enabled or repository.id not in policy.repository_ids:
        raise ValueError("Enable explicit Team enrollment for this repository first")
    if team.repository_ids and str(repository.id) not in team.repository_ids:
        raise ValueError("Repository is outside the Team's scope")
    if task.workspace_path or task.pull_request_number or task.manual_takeover or task.archived_at:
        raise ValueError("Existing task directories must be registered before starting work")
    if task.status not in {"NEW", "PAUSED", "WAITING_HUMAN"}:
        raise ValueError("Only new or suspended unstarted tasks can enroll")
    running = await session.scalar(
        select(Job.id).where(
            Job.task_id == task.id, Job.state.in_([JobState.CLAIMED, JobState.RUNNING])
        )
    )
    if running:
        raise ValueError("Stop the task's current worker before enrollment")
    profile = await session.scalar(
        select(TeamAgentProfile).where(
            TeamAgentProfile.team_id == task.team_id,
            TeamAgentProfile.role_kind == "DEVELOPER",
            TeamAgentProfile.enabled.is_(True),
        )
    )
    if (
        profile is None
        or profile.harness not in {"codex", "claude", "responses", "patch"}
        or profile.hard_budget_usd is None
    ):
        raise ValueError("Configure an enabled native Developer with an explicit USD limit")
    for job in await session.scalars(
        select(Job).where(
            Job.task_id == task.id,
            Job.state.in_([JobState.QUEUED, JobState.RETRY_WAIT, JobState.WAITING_PROVIDER]),
        )
    ):
        job.state = JobState.CANCELLED
        job.lease_token = job.lease_expires_at = None
    workspace = settings.workspace_root.resolve() / "tasks" / str(task.id) / "repository"
    native_state = settings.harness_state_root.resolve() / str(task.id)
    if workspace.exists() or native_state.exists():
        raise ValueError("Unregistered task directories require inspection before enrollment")
    task.status, task.stage, task.wait_reason = "NEW", "INTAKE", "NONE"
    task.lifecycle_version += 1
    session.add(
        TaskPhaseRun(
            task_id=task.id,
            status="NEW",
            stage="INTAKE",
            actor=actor,
            requirement_version=task.requirement_version,
        )
    )
    await enqueue_status(session, task.id, task.lifecycle_version, "NEW", "INTAKE")
    task.branch_name = f"agent/task-{task.id}"
    task.workspace_path = str(workspace)
    task.progress_fingerprint = {
        "requirement": requirement_fingerprint(task.title, task.description)
    }
    session.add(
        DeveloperSession(
            task_id=task.id,
            profile_id=profile.id,
            harness=profile.harness,
            harness_version=HARNESS_VERSIONS[profile.harness],
            provider=profile.provider,
            model=profile.model,
            workspace_path=str(workspace),
            state_path=str(native_state),
            requirement_version=task.requirement_version,
            checkpoint={"base_branch": repository.default_branch, "enrolled_by": actor},
        )
    )
    session.add(
        TaskEvent(
            task_id=task.id,
            source=actor,
            event_type="ENGINEERING_TASK_ENROLLED",
            payload={"repository_id": str(repository.id), "profile_id": str(profile.id)},
        )
    )
    await session.flush()
    await enqueue_phase(session, task)


def prepare_directories(workspace: Path, state: Path, task_id: str, settings: Settings) -> None:
    import os

    expected = settings.workspace_root.resolve() / "tasks" / task_id / "repository"
    if workspace != expected or state != settings.harness_state_root.resolve() / task_id:
        raise ValueError("Unexpected enrolled workspace paths")
    for path in (workspace, state):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("Task storage must not traverse symlinks")
        path.mkdir(parents=True, exist_ok=True)
        if os.getuid() == 0:
            os.chown(path, 10001, 10001)
