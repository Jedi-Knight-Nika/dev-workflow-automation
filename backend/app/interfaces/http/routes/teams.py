import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.bootstrap.dependencies import (
    get_team_management_workflow,
)
from app.interfaces.http.schemas.teams import (
    ShutdownTeamRead,
    TaskAssignmentCreate,
    TaskAssignmentRead,
    TeamRead,
    TeamWrite,
    WakeTeamRead,
)
from app.teams.application.manage_teams import ManageTeams
from app.teams.application.ports.team_management import (
    AssignTaskCommand,
    SaveTeamCommand,
    TeamConflict,
    TeamManagementWorkflow,
    TeamNotFound,
)

router = APIRouter(prefix="/teams", tags=["teams"])


def _team_command(body: TeamWrite) -> SaveTeamCommand:
    return SaveTeamCommand(
        body.name,
        body.description,
        body.enabled,
        body.max_concurrent_tasks,
        tuple(body.repository_ids),
    )


@router.get("", response_model=list[TeamRead])
async def list_teams(
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> list[TeamRead]:
    return [
        TeamRead.model_validate(item, from_attributes=True)
        for item in await ManageTeams(workflow).list()
    ]


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamWrite,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> TeamRead:
    try:
        result = await ManageTeams(workflow).create(_team_command(body))
    except (ValueError, TeamConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TeamRead.model_validate(result, from_attributes=True)


@router.get("/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: uuid.UUID,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> TeamRead:
    try:
        return TeamRead.model_validate(
            await ManageTeams(workflow).get(team_id), from_attributes=True
        )
    except TeamNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: uuid.UUID,
    body: TeamWrite,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> TeamRead:
    try:
        result = await ManageTeams(workflow).update(team_id, _team_command(body))
    except TeamNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, TeamConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TeamRead.model_validate(result, from_attributes=True)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_team(
    team_id: uuid.UUID,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> None:
    try:
        await ManageTeams(workflow).archive(team_id)
    except TeamNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TeamConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{team_id}/wake", response_model=WakeTeamRead)
async def wake_team(
    team_id: uuid.UUID,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> WakeTeamRead:
    try:
        result = await ManageTeams(workflow).wake(team_id)
    except TeamNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WakeTeamRead.model_validate(result, from_attributes=True)


@router.post("/{team_id}/shutdown", response_model=ShutdownTeamRead)
async def shutdown_team(
    team_id: uuid.UUID,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> ShutdownTeamRead:
    try:
        result = await ManageTeams(workflow).shutdown(team_id)
    except TeamNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ShutdownTeamRead.model_validate(result, from_attributes=True)


@router.get("/{team_id}/assignments", response_model=list[TaskAssignmentRead])
async def list_team_assignments(
    team_id: uuid.UUID,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> list[TaskAssignmentRead]:
    try:
        results = await ManageTeams(workflow).assignments(team_id)
    except TeamNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [TaskAssignmentRead.model_validate(item, from_attributes=True) for item in results]


@router.post("/{team_id}/assignments", response_model=TaskAssignmentRead, status_code=201)
async def assign_task(
    team_id: uuid.UUID,
    body: TaskAssignmentCreate,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> TaskAssignmentRead:
    try:
        result = await ManageTeams(workflow).assign(
            AssignTaskCommand(body.task_id, team_id, body.reason, body.start_work)
        )
    except TeamNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TeamConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TaskAssignmentRead.model_validate(result, from_attributes=True)


@router.delete("/assignments/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_task(
    task_id: uuid.UUID,
    workflow: TeamManagementWorkflow = Depends(get_team_management_workflow),
) -> None:
    try:
        await ManageTeams(workflow).unassign(task_id)
    except TeamNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TeamConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
