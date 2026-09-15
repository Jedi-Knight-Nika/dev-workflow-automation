from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.bootstrap.coordinator import coordination_administration as administration
from app.coordinator.application.ports import CoordinationAdministration
from app.interfaces.http.errors import service_errors

router = APIRouter(tags=["coordination"])


class HumanAnswer(BaseModel):
    request_id: UUID
    answer: str = Field(min_length=1, max_length=8000)


class PriorityChange(BaseModel):
    priority: int = Field(ge=0, le=5)


@router.get("/queue")
async def queue(
    team_id: UUID | None = None,
    offset: int = Query(default=0, ge=0, le=1000000),
    service: CoordinationAdministration = Depends(administration),
) -> dict[str, Any]:
    try:
        return await service.queue(team_id, offset)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/queue/teams/{team_id}")
async def team_queue(
    team_id: UUID,
    offset: int = Query(default=0, ge=0, le=1000000),
    service: CoordinationAdministration = Depends(administration),
) -> dict[str, Any]:
    try:
        return await service.queue(team_id, offset)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/tasks/{task_id}/coordinator")
async def task_coordinator(
    task_id: UUID, service: CoordinationAdministration = Depends(administration)
) -> dict[str, Any]:
    try:
        return await service.task(task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/tasks/{task_id}/human-request")
async def human_request(
    task_id: UUID, service: CoordinationAdministration = Depends(administration)
) -> Any:
    return (await task_coordinator(task_id, service))["human_request"]


@router.get("/tasks/{task_id}/actions")
async def task_actions(
    task_id: UUID, service: CoordinationAdministration = Depends(administration)
) -> Any:
    return (await task_coordinator(task_id, service))["actions"]


@router.post("/tasks/{task_id}/human-request/respond")
async def respond(
    task_id: UUID, body: HumanAnswer, service: CoordinationAdministration = Depends(administration)
) -> dict[str, str]:
    if not body.answer.strip():
        raise HTTPException(422, "Answer cannot be blank")
    with service_errors():
        await service.respond(task_id, body.request_id, body.answer.strip())
    return {"status": "QUEUED"}


@router.post("/tasks/{task_id}/priority")
async def priority(
    task_id: UUID,
    body: PriorityChange,
    service: CoordinationAdministration = Depends(administration),
) -> dict[str, str]:
    with service_errors():
        await service.priority(task_id, body.priority)
    return {"status": "UPDATED"}


@router.post("/tasks/{task_id}/actions/{action_id}/reconcile", status_code=202)
async def reconcile_action(
    task_id: UUID,
    action_id: UUID,
    service: CoordinationAdministration = Depends(administration),
) -> dict[str, str]:
    with service_errors():
        await service.reconcile(task_id, action_id)
    return {"status": "QUEUED"}


class ActionReview(BaseModel):
    verdict: Literal["CORRECT", "INCORRECT"]


@router.post("/tasks/{task_id}/actions/{action_id}/review")
async def review_action(
    task_id: UUID,
    action_id: UUID,
    body: ActionReview,
    service: CoordinationAdministration = Depends(administration),
) -> dict[str, str]:
    try:
        await service.review_action(task_id, action_id, body.verdict)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"status": "RECORDED"}
