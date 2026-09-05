import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.application.manage_terminal import ManageTerminal
from app.application.ports.terminal_sessions import OpenTerminalCommand, TerminalUnavailable
from app.bootstrap.dependencies import get_terminal_session_gateway
from app.infrastructure.persistence.terminal_sessions import SqlAlchemyTerminalSessionGateway
from app.infrastructure.terminal_runtime import terminal_runtime
from app.schemas import TerminalAccessRead, TerminalOpen

router = APIRouter(tags=["terminals"])


@router.post("/tasks/{task_id}/terminal", response_model=TerminalAccessRead)
async def open_terminal(
    task_id: uuid.UUID,
    body: TerminalOpen,
    gateway: SqlAlchemyTerminalSessionGateway = Depends(get_terminal_session_gateway),
) -> TerminalAccessRead:
    try:
        access = await ManageTerminal(gateway).open(
            OpenTerminalCommand(task_id, body.node_id, body.cols, body.rows)
        )
    except TerminalUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TerminalAccessRead.model_validate(access, from_attributes=True)


@router.delete("/terminal/{session_id}", status_code=204)
async def close_terminal(
    session_id: uuid.UUID,
    gateway: SqlAlchemyTerminalSessionGateway = Depends(get_terminal_session_gateway),
) -> None:
    if not await ManageTerminal(gateway).close(session_id):
        raise HTTPException(status_code=404, detail="Terminal session not found")


@router.websocket("/terminal/{session_id}/stream")
async def terminal_stream(websocket: WebSocket, session_id: uuid.UUID, token: str) -> None:
    try:
        await terminal_runtime.attach(session_id, token, websocket)
    except PermissionError:
        await websocket.close(code=4403, reason="Terminal session is invalid or expired")
    except WebSocketDisconnect:
        pass
