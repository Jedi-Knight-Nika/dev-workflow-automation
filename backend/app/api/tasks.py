import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    IndexStatus,
    Integration,
    Job,
    JobRole,
    JobState,
    Repository,
    ReviewFinding,
    Task,
    TaskEvent,
    TaskState,
    ValidationRecord,
)
from app.db.session import get_session
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth
from app.schemas import (
    EventRead,
    JobCreate,
    JobRead,
    MergeResult,
    PullRequestRead,
    ReviewFindingRead,
    TaskCreate,
    TaskRead,
    ValidationRead,
)
from app.services.crypto import cipher
from app.services.executor import workspace_fingerprint
from app.services.linear_sync import sync_merged_task_to_linear
from app.services.orchestrator import enqueue_job, record_event
from app.services.pull_requests import publish_pull_request
from app.services.workspaces import GitCommandError, prepare_workspace, run_git

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    limit: int = Query(default=100, ge=1, le=500), session: AsyncSession = Depends(get_session)
) -> list[Task]:
    return list(
        (await session.scalars(select(Task).order_by(Task.created_at.desc()).limit(limit))).all()
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreate, session: AsyncSession = Depends(get_session)) -> Task:
    task = Task(
        external_key=body.external_key,
        title=body.title,
        description=body.description,
        priority=body.priority,
        repository_id=body.repository_id,
    )
    session.add(task)
    await session.flush()
    await record_event(session, task.id, "TASK_CREATED", {"title": task.title}, source="api")
    if body.enqueue_planning:
        await enqueue_job(
            session,
            task,
            JobRole.INTAKE,
            "INTERPRET_TASK",
            payload={"source": "dashboard"},
        )
    await session.commit()
    await session.refresh(task)
    return task


@router.post("/{task_id}/workspace", response_model=TaskRead)
async def create_task_workspace(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.repository_id is None:
        raise HTTPException(status_code=409, detail="Task has no selected repository")
    repository = await session.get(Repository, task.repository_id)
    if repository is None or not repository.enabled:
        raise HTTPException(status_code=409, detail="Repository is unavailable")
    try:
        await prepare_workspace(session, task, repository)
    except GitCommandError as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=f"Git workspace failed: {exc}") from exc
    await record_event(
        session,
        task.id,
        "WORKSPACE_READY",
        {"branch": task.branch_name, "revision": task.current_revision},
    )
    await session.commit()
    return task


@router.post("/{task_id}/pull-request", response_model=PullRequestRead)
async def create_or_update_pull_request(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PullRequestRead:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.repository_id is None:
        raise HTTPException(status_code=409, detail="Task has no repository")
    repository = await session.get(Repository, task.repository_id)
    if repository is None:
        raise HTTPException(status_code=409, detail="Repository is unavailable")
    try:
        return await publish_pull_request(session, task, repository)
    except (GitCommandError, RuntimeError) as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{task_id}/validations", response_model=list[ValidationRead])
async def list_task_validations(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[ValidationRecord]:
    return list(
        (
            await session.scalars(
                select(ValidationRecord)
                .where(ValidationRecord.task_id == task_id)
                .order_by(ValidationRecord.created_at.desc())
            )
        ).all()
    )


@router.get("/{task_id}/findings", response_model=list[ReviewFindingRead])
async def list_task_findings(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[ReviewFinding]:
    return list(
        (
            await session.scalars(
                select(ReviewFinding)
                .where(ReviewFinding.task_id == task_id)
                .order_by(ReviewFinding.created_at.desc())
            )
        ).all()
    )


@router.post("/{task_id}/merge", response_model=MergeResult)
async def merge_task_pull_request(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> MergeResult:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.pull_request_number is None or task.repository_id is None or not task.current_revision:
        raise HTTPException(status_code=409, detail="Task has no publishable pull request")
    repository = await session.get(Repository, task.repository_id)
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    if repository is None or integration is None or integration.encrypted_credentials is None:
        raise HTTPException(status_code=409, detail="GitHub integration is unavailable")
    validations = list(
        (
            await session.scalars(
                select(ValidationRecord)
                .where(
                    ValidationRecord.task_id == task.id,
                    ValidationRecord.revision == task.current_revision,
                )
                .order_by(ValidationRecord.created_at.desc())
            )
        ).all()
    )
    latest = {(item.kind, item.name): item for item in reversed(validations)}
    checks = [item for item in latest.values() if item.kind in {"CHECK", "CHECK_SUITE", "STATUS"}]
    blocking = {
        "FAILURE",
        "FAILED",
        "ERROR",
        "CANCELLED",
        "TIMED_OUT",
        "ACTION_REQUIRED",
        "CHANGES_REQUESTED",
        "PENDING",
        "QUEUED",
        "IN_PROGRESS",
    }
    if not checks or any(item.status in blocking for item in latest.values()):
        raise HTTPException(
            status_code=409, detail="Latest revision has incomplete or failing gates"
        )
    auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
    client = GitHubClient(auth.token, auth.installation)
    try:
        pull_request = await client.get_pull_request(
            repository.owner, repository.name, task.pull_request_number
        )
        if pull_request.head_sha != task.current_revision:
            expected_revision = task.current_revision
            task.current_revision = pull_request.head_sha
            task.state = TaskState.WAITING_GITHUB
            await record_event(
                session,
                task.id,
                "MERGE_REJECTED_STALE_SHA",
                {"expected": expected_revision, "actual": pull_request.head_sha},
            )
            await session.commit()
            raise HTTPException(status_code=409, detail="PR head changed; validations are stale")
        result = await client.merge_pull_request(
            repository.owner,
            repository.name,
            task.pull_request_number,
            task.current_revision,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub merge failed: {exc}") from exc
    if not result.merged:
        raise HTTPException(status_code=409, detail=result.message)
    task.state = TaskState.MERGED
    task.current_revision = result.sha or task.current_revision
    repository.index_status = IndexStatus.QUEUED
    repository.index_error = None
    await record_event(session, task.id, "PULL_REQUEST_MERGED", result.model_dump(mode="json"))
    await session.commit()
    await sync_merged_task_to_linear(session, task)
    return result


@router.post("/{task_id}/linear-sync")
async def retry_linear_sync(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, bool]:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.state != TaskState.MERGED:
        raise HTTPException(status_code=409, detail="Only merged tasks can be synchronized")
    return {"synchronized": await sync_merged_task_to_linear(session, task)}


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/jobs", response_model=list[JobRead])
async def list_task_jobs(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[Job]:
    return list(
        (
            await session.scalars(
                select(Job).where(Job.task_id == task_id).order_by(Job.created_at)
            )
        ).all()
    )


@router.post("/{task_id}/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    task_id: uuid.UUID, body: JobCreate, session: AsyncSession = Depends(get_session)
) -> Job:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.state in (TaskState.CANCELLED, TaskState.PAUSED):
        raise HTTPException(
            status_code=409, detail=f"Cannot enqueue work for {task.state.value} task"
        )
    job = await enqueue_job(session, task, body.role, body.action, body.priority, body.payload)
    await session.commit()
    await session.refresh(job)
    return job


@router.get("/{task_id}/events", response_model=list[EventRead])
async def list_task_events(
    task_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[TaskEvent]:
    return list(
        (
            await session.scalars(
                select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id)
            )
        ).all()
    )


@router.post("/{task_id}/pause", response_model=TaskRead)
async def pause_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.state = TaskState.PAUSED
    await record_event(session, task.id, "TASK_PAUSED", {}, source="user")
    await session.commit()
    return task


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.state = TaskState.CANCELLED
    queued = (
        await session.scalars(
            select(Job).where(Job.task_id == task.id, Job.state == JobState.QUEUED)
        )
    ).all()
    for job in queued:
        job.state = JobState.CANCELLED
    await record_event(
        session, task.id, "TASK_CANCELLED", {"cancelled_jobs": len(queued)}, source="user"
    )
    await session.commit()
    return task


@router.post("/{task_id}/takeover", response_model=TaskRead)
async def take_over_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.state in {TaskState.CANCELLED, TaskState.MERGED}:
        raise HTTPException(status_code=409, detail=f"Cannot take over a {task.state.value} task")
    task.manual_takeover = True
    task.state = TaskState.PAUSED
    queued = list(
        (
            await session.scalars(
                select(Job).where(Job.task_id == task.id, Job.state == JobState.QUEUED)
            )
        ).all()
    )
    for job in queued:
        job.state = JobState.CANCELLED
    await record_event(
        session,
        task.id,
        "MANUAL_TAKEOVER_STARTED",
        {"cancelled_queued_jobs": len(queued), "workspace_path": task.workspace_path},
        source="user",
    )
    await session.commit()
    return task


@router.post("/{task_id}/resume", response_model=TaskRead)
async def resume_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.manual_takeover:
        raise HTTPException(status_code=409, detail="Task is not under manual control")
    fingerprint = None
    if task.workspace_path:
        workspace = Path(task.workspace_path)
        try:
            task.current_revision = await run_git("rev-parse", "HEAD", cwd=workspace)
            fingerprint = await workspace_fingerprint(workspace)
        except GitCommandError as exc:
            raise HTTPException(status_code=409, detail=f"Workspace refresh failed: {exc}") from exc
    task.manual_takeover = False
    task.state = (
        TaskState.WAITING_GITHUB if task.pull_request_number else TaskState.LOCAL_VALIDATION
    )
    await record_event(
        session,
        task.id,
        "MANUAL_TAKEOVER_ENDED",
        {"revision": task.current_revision, "workspace_fingerprint": fingerprint},
        source="user",
    )
    await session.commit()
    return task
