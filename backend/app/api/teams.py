import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.design_workflow import DesignWorkflow
from app.application.manage_teams import ManageTeams
from app.application.ports.model_validation import ModelValidationGateway, NodeModelValidationStore
from app.application.ports.team_management import (
    AssignTaskCommand,
    SaveTeamCommand,
    TeamConflict,
    TeamManagementWorkflow,
    TeamNotFound,
)
from app.application.ports.workflow_designer import WorkflowDesigner, WorkflowVersionConflict
from app.application.validate_node_model import ValidateNodeModel
from app.bootstrap.dependencies import (
    get_provider_catalog_workflow,
    get_team_management_workflow,
    get_team_workflow_designer,
)
from app.domain.workflows import WorkflowEdgeData, WorkflowGraphData, WorkflowNodeData
from app.schemas import (
    TaskAssignmentCreate,
    TaskAssignmentRead,
    TeamRead,
    TeamWrite,
    WorkflowGraphRead,
    WorkflowNodeModelValidationRead,
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


def _graph_response(graph: WorkflowGraphData) -> WorkflowGraphRead:
    return WorkflowGraphRead.model_validate(
        {
            "version": graph.version,
            "nodes": [asdict(node) for node in graph.nodes],
            "edges": [asdict(edge) for edge in graph.edges],
        }
    )


def _graph_data(body: WorkflowGraphRead) -> WorkflowGraphData:
    return WorkflowGraphData(
        body.version,
        tuple(
            WorkflowNodeData(
                str(node.id),
                node.role,
                node.label,
                node.position_x,
                node.position_y,
                node.enabled,
                node.activation_policy,
                node.batch_window_seconds,
                tuple(str(item) for item in node.integration_ids),
                tuple(str(item) for item in node.repository_ids),
                node.provider,
                node.model,
                node.system_prompt,
                node.model_validation_status,
                node.model_validation_message,
                node.model_validated_at,
                node.integration_mode,
                node.poll_interval_seconds,
                node.filter_assignee_id,
                tuple(node.filter_state_ids),
                node.integration_sync_status,
                node.integration_sync_error,
                node.integration_last_synced_at,
                node.reasoning_effort,
                node.max_output_tokens,
                node.temperature,
                node.timeout_minutes,
                node.max_retries,
                node.max_review_cycles,
                node.context_depth,
                node.rag_retrieval_depth,
                node.fallback_provider,
                node.fallback_model,
                str(node.agent_id) if node.agent_id else None,
            )
            for node in body.nodes
        ),
        tuple(
            WorkflowEdgeData(
                str(edge.id),
                str(edge.source_node_id),
                str(edge.target_node_id),
                edge.outcome,
                edge.required,
            )
            for edge in body.edges
        ),
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
            AssignTaskCommand(body.task_id, team_id, body.reason)
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


@router.get("/{team_id}/workflow", response_model=WorkflowGraphRead)
async def get_team_workflow(
    designer: WorkflowDesigner = Depends(get_team_workflow_designer),
) -> WorkflowGraphRead:
    return _graph_response(await DesignWorkflow(designer).get())


@router.put("/{team_id}/workflow", response_model=WorkflowGraphRead)
async def update_team_workflow(
    body: WorkflowGraphRead,
    designer: WorkflowDesigner = Depends(get_team_workflow_designer),
) -> WorkflowGraphRead:
    try:
        return _graph_response(await DesignWorkflow(designer).replace(_graph_data(body)))
    except WorkflowVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{team_id}/workflow/nodes/{node_id}/validate-model",
    response_model=WorkflowNodeModelValidationRead,
)
async def validate_team_node_model(
    node_id: uuid.UUID,
    designer: NodeModelValidationStore = Depends(get_team_workflow_designer),
    gateway: ModelValidationGateway = Depends(get_provider_catalog_workflow),
) -> WorkflowNodeModelValidationRead:
    try:
        result = await ValidateNodeModel(designer, gateway).execute(str(node_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WorkflowNodeModelValidationRead.model_validate(result, from_attributes=True)
