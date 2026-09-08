import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.bootstrap.dependencies import (
    get_task_conversation_store,
    get_task_history_queries,
    get_task_lifecycle_factory,
    get_task_queries,
    get_unit_of_work,
)
from app.engineering.application.change_lifecycle import ChangeTaskLifecycle, TaskNotFound
from app.engineering.application.create_task import CreateTask, CreateTaskCommand
from app.engineering.application.manage_task_conversation import (
    AddTaskMessage,
    QueryTaskConversation,
)
from app.engineering.application.ports.task_conversation import TaskConversationStore
from app.engineering.application.ports.task_history import TaskHistoryQueries
from app.engineering.application.ports.task_lifecycle import (
    TaskLifecycleUnitOfWorkFactory,
)
from app.engineering.application.ports.task_queries import TaskListFilters, TaskQueries, TaskView
from app.engineering.application.ports.unit_of_work import UnitOfWork
from app.engineering.application.query_history import QueryTaskHistory
from app.engineering.application.query_tasks import GetTask, ListTasks
from app.engineering.domain.controls import LifecycleAction
from app.engineering.domain.lifecycle import InvalidTransition, TaskStatus
from app.interfaces.http.schemas.tasks import (
    EventRead,
    JobRead,
    TaskCreate,
    TaskMessageCreate,
    TaskMessagePageRead,
    TaskMessageRead,
    TaskMetricsRead,
    TaskRead,
)
from app.interfaces.http.schemas.workers import ValidationRead

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
            "project_name": view.project_name,
            "labels": view.labels,
            "estimate": view.estimate,
            "repository_scopes": [asdict(scope) for scope in view.repository_scopes],
        }
    )


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None, max_length=200),
    status: list[TaskStatus] = Query(default=[]),
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
        tuple(status),
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
            start_work=body.start_work,
            project_name=body.project_name,
            labels=tuple(body.labels),
            estimate=body.estimate,
            due_at=body.due_at,
        )
    )
    return TaskRead.model_validate(task)


@router.get("/{task_id}/validations", response_model=list[ValidationRead])
async def list_task_validations(
    task_id: uuid.UUID,
    queries: TaskHistoryQueries = Depends(get_task_history_queries),
) -> list[ValidationRead]:
    items = await QueryTaskHistory(queries).validations(task_id)
    return [ValidationRead.model_validate(item) for item in items]


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


@router.get("/{task_id}/metrics", response_model=TaskMetricsRead)
async def task_metrics(
    task_id: uuid.UUID,
    queries: TaskHistoryQueries = Depends(get_task_history_queries),
) -> TaskMetricsRead:
    return TaskMetricsRead.model_validate(await queries.metrics(task_id), from_attributes=True)


@router.get("/{task_id}/runs")
async def native_runs(
    task_id: uuid.UUID,
    queries: TaskHistoryQueries = Depends(get_task_history_queries),
) -> list[dict[str, Any]]:
    return [asdict(run) for run in await queries.runs(task_id)]


@router.get("/{task_id}/events", response_model=list[EventRead])
async def list_task_events(
    task_id: uuid.UUID,
    queries: TaskHistoryQueries = Depends(get_task_history_queries),
) -> list[EventRead]:
    items = await QueryTaskHistory(queries).events(task_id)
    return [EventRead.model_validate(item) for item in items]


@router.get("/{task_id}/messages", response_model=TaskMessagePageRead)
async def list_task_messages(
    task_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None, ge=1),
    store: TaskConversationStore = Depends(get_task_conversation_store),
) -> TaskMessagePageRead:
    page = await QueryTaskConversation(store).execute(task_id, limit, before_id)
    return TaskMessagePageRead.model_validate(asdict(page))


@router.post(
    "/{task_id}/messages", response_model=TaskMessageRead, status_code=status.HTTP_201_CREATED
)
async def add_task_message(
    task_id: uuid.UUID,
    body: TaskMessageCreate,
    store: TaskConversationStore = Depends(get_task_conversation_store),
) -> TaskMessageRead:
    try:
        message = await AddTaskMessage(store).execute(task_id, body.body, body.reply_to_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TaskMessageRead.model_validate(message)


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


@router.post("/{task_id}/archive", response_model=TaskRead)
async def archive_task(
    task_id: uuid.UUID,
    factory: TaskLifecycleUnitOfWorkFactory = Depends(get_task_lifecycle_factory),
) -> TaskRead:
    return await _change_lifecycle(task_id, LifecycleAction.ARCHIVE, factory)


async def _change_lifecycle(
    task_id: uuid.UUID, action: LifecycleAction, factory: TaskLifecycleUnitOfWorkFactory
) -> TaskRead:
    try:
        task = await ChangeTaskLifecycle(factory).execute(task_id, action)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TaskRead.model_validate(task)
