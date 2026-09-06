import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.application.manage_agent_runtime import ManageAgentRuntime
from app.application.ports.agent_runtime import AgentRuntimeNotFound, AgentRuntimeStore
from app.bootstrap.dependencies import get_agent_runtime_store

router = APIRouter(prefix="/agent-runtime", tags=["agent-runtime"])


@router.get("/{agent_id}")
async def effective_agent_runtime(
    agent_id: uuid.UUID,
    store: AgentRuntimeStore = Depends(get_agent_runtime_store),
) -> dict[str, Any]:
    try:
        return await ManageAgentRuntime(store).get(agent_id)
    except AgentRuntimeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{agent_id}/overrides")
async def update_agent_runtime(
    agent_id: uuid.UUID,
    body: dict[str, Any],
    store: AgentRuntimeStore = Depends(get_agent_runtime_store),
) -> dict[str, Any]:
    try:
        return await ManageAgentRuntime(store).update(agent_id, body)
    except AgentRuntimeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{agent_id}/overrides")
async def reset_agent_runtime(
    agent_id: uuid.UUID,
    store: AgentRuntimeStore = Depends(get_agent_runtime_store),
) -> dict[str, Any]:
    try:
        return await ManageAgentRuntime(store).reset(agent_id)
    except AgentRuntimeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
