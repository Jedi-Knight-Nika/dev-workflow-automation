import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.ports.job_enqueueing import JobEnqueueWorkflow
from app.application.ports.merge_workflow import MergeWorkflow
from app.application.ports.pull_request_publication import (
    PublishConflict,
    PublishTaskNotFound,
    PublishUnavailable,
    PullRequestPublicationWorkflow,
)
from app.application.ports.task_history import TaskHistoryQueries
from app.application.ports.task_lifecycle import (
    TaskLifecycleUnitOfWorkFactory,
    WorkspaceRefreshUnavailable,
)
from app.application.ports.task_queries import TaskListFilters, TaskQueries, TaskView
from app.application.ports.tracker_sync import (
    TrackerSyncConflict,
    TrackerSyncWorkflow,
    TrackerTaskNotFound,
)
from app.application.ports.unit_of_work import UnitOfWork
from app.application.ports.workspace_workflow import (
    WorkspaceConflict,
    WorkspaceTaskNotFound,
    WorkspaceUnavailable,
    WorkspaceWorkflow,
)
from app.application.pull_requests import (
    MergeConflict,
    MergeTask,
    MergeTaskNotFound,
    MergeUnavailable,
    PublishTaskPullRequest,
)
from app.application.tasks import (
    ChangeTaskLifecycle,
    CreateTask,
    CreateTaskCommand,
    GetTask,
    ListTasks,
    PrepareTaskWorkspace,
    QueryTaskHistory,
    SynchronizeMergedTask,
    TaskNotFound,
)
from app.bootstrap.dependencies import (
    get_job_enqueue_workflow,
    get_merge_workflow,
    get_pull_request_publication_workflow,
    get_task_history_queries,
    get_task_lifecycle_factory,
    get_task_queries,
    get_tracker_sync_workflow,
    get_unit_of_work,
    get_workspace_workflow,
)
from app.domain.tasks import InvalidTaskTransition, LifecycleAction, TaskState
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

router = APIRouter(prefix="/tasks", tags=["tasks"])


def task_view_response(view: TaskView) -> TaskRead:
    return TaskRead.model_validate(
        {
            **asdict(view.task),
            "source": asdict(view.source) if view.source else None,
            "repository_name": view.repository_name,
            "due_at": view.due_at,
            "started_at": view.started_at,
            "completed_at": view.completed_at,
            "team_id": view.team_id,
            "team_name": view.team_name,
        }
    )


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, max_length=200),
    state: list[TaskState] = Query(default=[]),
    provider: str | None = Query(default=None, max_length=50),
    repository_id: uuid.UUID | None = None,
    priority: list[int] = Query(default=[]),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
    assignee: str | None = Query(default=None, max_length=200),
    team: str | None = Query(default=None, max_length=200),
    project: str | None = Query(default=None, max_length=200),
    label: str | None = Query(default=None, max_length=200),
    provider_state: str | None = Query(default=None, max_length=200),
    assigned_team_id: uuid.UUID | None = None,
    unassigned: bool = False,
    sort: Literal["priority", "created", "updated", "due"] = "priority",
    direction: Literal["asc", "desc"] = "asc",
    queries: TaskQueries = Depends(get_task_queries),
) -> list[TaskRead]:
    filters = TaskListFilters(
        search,
        tuple(state),
        provider,
        repository_id,
        tuple(priority),
        created_from,
        created_to,
        due_from,
        due_to,
        updated_from,
        updated_to,
        assignee,
        team,
        project,
        label,
        provider_state,
        assigned_team_id,
        unassigned,
        sort,
        direction,
    )
    return [task_view_response(task) for task in await ListTasks(queries).execute(limit, filters)]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    unit_of_work: UnitOfWork = Depends(get_unit_of_work),
) -> TaskRead:
    task = await CreateTask(unit_of_work).execute(
        CreateTaskCommand(
            external_key=body.external_key,
            title=body.title,
            description=body.description,
            priority=body.priority,
            repository_id=body.repository_id,
            enqueue_planning=body.enqueue_planning,
        )
    )
    return TaskRead.model_validate(task)


@router.post("/{task_id}/workspace", response_model=TaskRead)
async def create_task_workspace(
    task_id: uuid.UUID,
    workflow: WorkspaceWorkflow = Depends(get_workspace_workflow),
) -> TaskRead:
    try:
        task = await PrepareTaskWorkspace(workflow).execute(task_id)
    except WorkspaceTaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkspaceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkspaceUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TaskRead.model_validate(task)


@router.post("/{task_id}/pull-request", response_model=PullRequestRead)
async def create_or_update_pull_request(
    task_id: uuid.UUID,
    workflow: PullRequestPublicationWorkflow = Depends(get_pull_request_publication_workflow),
) -> PullRequestRead:
    try:
        result = await PublishTaskPullRequest(workflow).execute(task_id)
    except PublishTaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublishConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PublishUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PullRequestRead.model_validate(result)


@router.get("/{task_id}/validations", response_model=list[ValidationRead])
async def list_task_validations(
    task_id: uuid.UUID,
    queries: TaskHistoryQueries = Depends(get_task_history_queries),
) -> list[ValidationRead]:
    items = await QueryTaskHistory(queries).validations(task_id)
    return [ValidationRead.model_validate(item) for item in items]


@router.get("/{task_id}/findings", response_model=list[ReviewFindingRead])
async def list_task_findings(
    task_id: uuid.UUID,
    queries: TaskHistoryQueries = Depends(get_task_history_queries),
) -> list[ReviewFindingRead]:
    items = await QueryTaskHistory(queries).findings(task_id)
    return [ReviewFindingRead.model_validate(item) for item in items]


@router.post("/{task_id}/merge", response_model=MergeResult)
async def merge_task_pull_request(
    task_id: uuid.UUID,
    workflow: MergeWorkflow = Depends(get_merge_workflow),
) -> MergeResult:
    try:
        result = await MergeTask(workflow).execute(task_id)
    except MergeTaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (MergeConflict, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MergeUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MergeResult(merged=result.merged, sha=result.sha, message=result.message)


@router.post("/{task_id}/linear-sync")
async def retry_linear_sync(
    task_id: uuid.UUID,
    workflow: TrackerSyncWorkflow = Depends(get_tracker_sync_workflow),
) -> dict[str, bool]:
    try:
        synchronized = await SynchronizeMergedTask(workflow).execute(task_id)
    except TrackerTaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TrackerSyncConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"synchronized": synchronized}


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: uuid.UUID,
    queries: TaskQueries = Depends(get_task_queries),
) -> TaskRead:
    try:
        task = await GetTask(queries).execute(task_id)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return task_view_response(task)


@router.get("/{task_id}/jobs", response_model=list[JobRead])
async def list_task_jobs(
    task_id: uuid.UUID,
    queries: TaskHistoryQueries = Depends(get_task_history_queries),
) -> list[JobRead]:
    items = await QueryTaskHistory(queries).jobs(task_id)
    return [JobRead.model_validate(item) for item in items]


@router.post("/{task_id}/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    task_id: uuid.UUID,
    body: JobCreate,
    workflow: JobEnqueueWorkflow = Depends(get_job_enqueue_workflow),
) -> JobRead:
    try:
        job = await EnqueueTaskJob(workflow).execute(
            EnqueueJobCommand(
                task_id=task_id,
                role=body.role.value,
                action=body.action,
                priority=body.priority,
                payload=body.payload,
            )
        )
    except EnqueueTaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnqueueTaskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobRead.model_validate(job)


@router.get("/{task_id}/events", response_model=list[EventRead])
async def list_task_events(
    task_id: uuid.UUID,
    queries: TaskHistoryQueries = Depends(get_task_history_queries),
) -> list[EventRead]:
    items = await QueryTaskHistory(queries).events(task_id)
    return [EventRead.model_validate(item) for item in items]


@router.post("/{task_id}/pause", response_model=TaskRead)
async def pause_task(
    task_id: uuid.UUID,
    factory: TaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.PAUSE, factory)


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(
    task_id: uuid.UUID,
    factory: TaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.CANCEL, factory)


@router.post("/{task_id}/takeover", response_model=TaskRead)
async def take_over_task(
    task_id: uuid.UUID,
    factory: TaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.TAKEOVER, factory)


@router.post("/{task_id}/resume", response_model=TaskRead)
async def resume_task(
    task_id: uuid.UUID,
    factory: TaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.RESUME, factory)


async def _change_lifecycle(
    task_id: uuid.UUID, action: LifecycleAction, factory: TaskLifecycleUnitOfWorkFactory
) -> TaskRead:
    try:
        task = await ChangeTaskLifecycle(factory).execute(task_id, action)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkspaceRefreshUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TaskRead.model_validate(task)


from app.application.jobs import EnqueueTaskJob
from app.application.ports.job_enqueueing import (
    EnqueueJobCommand,
    EnqueueTaskConflict,
    EnqueueTaskNotFound,
)
