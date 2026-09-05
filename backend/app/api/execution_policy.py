import platform
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.application.manage_execution_policy import ManageExecutionPolicy
from app.application.ports.execution_policy import ExecutionPolicyStore
from app.bootstrap.dependencies import get_execution_policy_store
from app.config import Settings, get_settings
from app.domain.security import CAPABILITY_CATALOG, Decision, ExecutionMode, TeamExecutionPolicy
from app.schemas import ApprovalResolution, ExecutionPolicyRead, ExecutionPolicyWrite

router = APIRouter(tags=["execution-policy"])


def response(policy: TeamExecutionPolicy, settings: Settings) -> ExecutionPolicyRead:
    containerized = settings.worker_transport == "docker" or Path("/.dockerenv").exists()
    return ExecutionPolicyRead(
        mode=policy.mode.value,
        settings={key: value.value for key, value in policy.settings.items()},
        approved_hosts=list(policy.approved_hosts),
        max_command_timeout_seconds=policy.max_command_timeout_seconds,
        max_output_bytes=policy.max_output_bytes,
        isolation_level="MEDIUM" if containerized else "REDUCED",
        execution_environment="CONTAINER" if containerized else platform.system().upper(),
    )


@router.get("/teams/{team_id}/execution-policy", response_model=ExecutionPolicyRead)
async def get_policy(
    team_id: uuid.UUID,
    store: ExecutionPolicyStore = Depends(get_execution_policy_store),
    settings: Settings = Depends(get_settings),
) -> ExecutionPolicyRead:
    try:
        return response(await ManageExecutionPolicy(store).get(team_id), settings)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/teams/{team_id}/execution-policy", response_model=ExecutionPolicyRead)
async def save_policy(
    team_id: uuid.UUID,
    body: ExecutionPolicyWrite,
    store: ExecutionPolicyStore = Depends(get_execution_policy_store),
    runtime_settings: Settings = Depends(get_settings),
) -> ExecutionPolicyRead:
    try:
        settings = {key: Decision(value) for key, value in body.settings.items()}
        policy = TeamExecutionPolicy(
            ExecutionMode(body.mode),
            settings,
            tuple(body.approved_hosts),
            body.max_command_timeout_seconds,
            body.max_output_bytes,
        )
        return response(await ManageExecutionPolicy(store).save(team_id, policy), runtime_settings)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/execution-capabilities")
async def capabilities() -> list[str]:
    return sorted(CAPABILITY_CATALOG)


@router.get("/approvals")
async def approvals(
    store: ExecutionPolicyStore = Depends(get_execution_policy_store),
    state: str | None = Query(default=None),
) -> list[dict[str, object]]:
    return [asdict(item) for item in await ManageExecutionPolicy(store).approvals(state)]


@router.post("/approvals/{approval_id}/approve")
async def approve(
    approval_id: uuid.UUID,
    body: ApprovalResolution,
    store: ExecutionPolicyStore = Depends(get_execution_policy_store),
) -> dict[str, object]:
    try:
        return asdict(
            await ManageExecutionPolicy(store).resolve(
                approval_id, True, body.resolved_by, body.scope
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/deny")
async def deny(
    approval_id: uuid.UUID,
    body: ApprovalResolution,
    store: ExecutionPolicyStore = Depends(get_execution_policy_store),
) -> dict[str, object]:
    try:
        return asdict(
            await ManageExecutionPolicy(store).resolve(
                approval_id, False, body.resolved_by, body.scope
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/tool-events")
async def task_tool_events(
    task_id: uuid.UUID, store: ExecutionPolicyStore = Depends(get_execution_policy_store)
) -> list[dict[str, object]]:
    return [
        asdict(item) for item in await ManageExecutionPolicy(store).tool_events(task_id=task_id)
    ]


@router.get("/jobs/{job_id}/tool-events")
async def job_tool_events(
    job_id: uuid.UUID, store: ExecutionPolicyStore = Depends(get_execution_policy_store)
) -> list[dict[str, object]]:
    return [asdict(item) for item in await ManageExecutionPolicy(store).tool_events(job_id=job_id)]
