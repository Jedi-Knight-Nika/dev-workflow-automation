import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.manage_roles import ManageRoles
from app.application.ports.role_management import (
    RoleConflict,
    RoleManagementWorkflow,
    RoleNotFound,
    SaveRoleCommand,
)
from app.bootstrap.dependencies import get_role_management_workflow
from app.domain.roles import ROLE_CAPABILITIES, ROLE_PERMISSIONS
from app.schemas import RoleClone, RoleRead, RoleWrite

router = APIRouter(prefix="/roles", tags=["roles"])


def command(body: RoleWrite) -> SaveRoleCommand:
    return SaveRoleCommand(
        body.name,
        body.category,
        body.description,
        body.system_instructions,
        tuple(body.capabilities),
        tuple(body.permissions),
        tuple(body.allowed_results),
        tuple(body.knowledge_collection_ids),
        body.default_provider,
        body.default_model,
        body.default_reasoning_effort,
        body.default_timeout_minutes,
        body.default_max_retries,
        body.enabled,
        body.runtime_profile.model_dump(mode="json"),
        body.override_policy.model_dump(mode="json"),
    )


def response(value: object) -> RoleRead:
    return RoleRead.model_validate(value, from_attributes=True)


@router.get("", response_model=list[RoleRead])
async def list_roles(
    workflow: RoleManagementWorkflow = Depends(get_role_management_workflow),
) -> list[RoleRead]:
    return [response(item) for item in await ManageRoles(workflow).list()]


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: uuid.UUID,
    workflow: RoleManagementWorkflow = Depends(get_role_management_workflow),
) -> RoleRead:
    try:
        return response(await ManageRoles(workflow).get(role_id))
    except RoleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=RoleRead, status_code=201)
async def create_role(
    body: RoleWrite, workflow: RoleManagementWorkflow = Depends(get_role_management_workflow)
) -> RoleRead:
    try:
        return response(await ManageRoles(workflow).create(command(body)))
    except (ValueError, RoleConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: uuid.UUID,
    body: RoleWrite,
    workflow: RoleManagementWorkflow = Depends(get_role_management_workflow),
) -> RoleRead:
    try:
        return response(await ManageRoles(workflow).update(role_id, command(body)))
    except RoleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RoleConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{role_id}/clone", response_model=RoleRead, status_code=201)
async def clone_role(
    role_id: uuid.UUID,
    body: RoleClone,
    workflow: RoleManagementWorkflow = Depends(get_role_management_workflow),
) -> RoleRead:
    try:
        return response(await ManageRoles(workflow).clone(role_id, body.name))
    except RoleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RoleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{role_id}/disable", response_model=RoleRead)
async def disable_role(
    role_id: uuid.UUID, workflow: RoleManagementWorkflow = Depends(get_role_management_workflow)
) -> RoleRead:
    try:
        return response(await ManageRoles(workflow).disable(role_id))
    except RoleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID, workflow: RoleManagementWorkflow = Depends(get_role_management_workflow)
) -> None:
    try:
        await ManageRoles(workflow).delete(role_id)
    except RoleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RoleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/catalog/permissions", response_model=list[str])
async def permissions_catalog() -> list[str]:
    return sorted(ROLE_PERMISSIONS)


@router.get("/catalog/capabilities", response_model=list[str])
async def capabilities_catalog() -> list[str]:
    return sorted(ROLE_CAPABILITIES)
