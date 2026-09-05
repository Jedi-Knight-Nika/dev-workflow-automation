import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.ports.pull_request_publication import (
    PublishConflict,
    PublishTaskNotFound,
    PublishUnavailable,
)
from app.application.ports.task_lifecycle import WorkspaceRefreshUnavailable
from app.application.ports.tracker_sync import TrackerSyncConflict, TrackerTaskNotFound
from app.application.ports.workspace_workflow import (
    WorkspaceConflict,
    WorkspaceTaskNotFound,
    WorkspaceUnavailable,
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
from app.domain.tasks import InvalidTaskTransition, LifecycleAction
from app.infrastructure.persistence import SqlAlchemyUnitOfWork
from app.infrastructure.persistence.job_enqueueing import SqlAlchemyJobEnqueueWorkflow
from app.infrastructure.persistence.task_history import SqlAlchemyTaskHistoryQueries
from app.infrastructure.persistence.task_lifecycle import SqlAlchemyTaskLifecycleUnitOfWorkFactory
from app.infrastructure.persistence.task_queries import SqlAlchemyTaskQueries
from app.infrastructure.persistence.tracker_sync import SqlAlchemyLinearSyncWorkflow
from app.infrastructure.pull_requests import (
    SqlAlchemyGitHubMergeWorkflow,
    SqlAlchemyGitHubPublicationWorkflow,
)
from app.infrastructure.workspaces import SqlAlchemyGitWorkspaceWorkflow
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


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    queries: SqlAlchemyTaskQueries = Depends(get_task_queries),
) -> list[TaskRead]:
    return [TaskRead.model_validate(task) for task in await ListTasks(queries).execute(limit)]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    unit_of_work: SqlAlchemyUnitOfWork = Depends(get_unit_of_work),
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
    workflow: SqlAlchemyGitWorkspaceWorkflow = Depends(get_workspace_workflow),
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
    workflow: SqlAlchemyGitHubPublicationWorkflow = Depends(get_pull_request_publication_workflow),
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
    queries: SqlAlchemyTaskHistoryQueries = Depends(get_task_history_queries),
) -> list[ValidationRead]:
    items = await QueryTaskHistory(queries).validations(task_id)
    return [ValidationRead.model_validate(item) for item in items]


@router.get("/{task_id}/findings", response_model=list[ReviewFindingRead])
async def list_task_findings(
    task_id: uuid.UUID,
    queries: SqlAlchemyTaskHistoryQueries = Depends(get_task_history_queries),
) -> list[ReviewFindingRead]:
    items = await QueryTaskHistory(queries).findings(task_id)
    return [ReviewFindingRead.model_validate(item) for item in items]


@router.post("/{task_id}/merge", response_model=MergeResult)
async def merge_task_pull_request(
    task_id: uuid.UUID,
    workflow: SqlAlchemyGitHubMergeWorkflow = Depends(get_merge_workflow),
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
    workflow: SqlAlchemyLinearSyncWorkflow = Depends(get_tracker_sync_workflow),
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
    queries: SqlAlchemyTaskQueries = Depends(get_task_queries),
) -> TaskRead:
    try:
        task = await GetTask(queries).execute(task_id)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TaskRead.model_validate(task)


@router.get("/{task_id}/jobs", response_model=list[JobRead])
async def list_task_jobs(
    task_id: uuid.UUID,
    queries: SqlAlchemyTaskHistoryQueries = Depends(get_task_history_queries),
) -> list[JobRead]:
    items = await QueryTaskHistory(queries).jobs(task_id)
    return [JobRead.model_validate(item) for item in items]


@router.post("/{task_id}/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    task_id: uuid.UUID,
    body: JobCreate,
    workflow: SqlAlchemyJobEnqueueWorkflow = Depends(get_job_enqueue_workflow),
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
    queries: SqlAlchemyTaskHistoryQueries = Depends(get_task_history_queries),
) -> list[EventRead]:
    items = await QueryTaskHistory(queries).events(task_id)
    return [EventRead.model_validate(item) for item in items]


@router.post("/{task_id}/pause", response_model=TaskRead)
async def pause_task(
    task_id: uuid.UUID,
    factory: SqlAlchemyTaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.PAUSE, factory)


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(
    task_id: uuid.UUID,
    factory: SqlAlchemyTaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.CANCEL, factory)


@router.post("/{task_id}/takeover", response_model=TaskRead)
async def take_over_task(
    task_id: uuid.UUID,
    factory: SqlAlchemyTaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.TAKEOVER, factory)


@router.post("/{task_id}/resume", response_model=TaskRead)
async def resume_task(
    task_id: uuid.UUID,
    factory: SqlAlchemyTaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.RESUME, factory)


async def _change_lifecycle(
    task_id: uuid.UUID, action: LifecycleAction, factory: SqlAlchemyTaskLifecycleUnitOfWorkFactory
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
