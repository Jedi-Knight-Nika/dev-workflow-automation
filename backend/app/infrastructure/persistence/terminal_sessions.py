import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.terminal_sessions import (
    OpenTerminalCommand,
    TerminalAccess,
    TerminalUnavailable,
)
from app.db.models import Job, JobState, Task, TerminalSession


def terminal_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SqlAlchemyTerminalSessionGateway:
    def __init__(self, session: AsyncSession, workspace_root: Path) -> None:
        self._session = session
        self._workspace_root = workspace_root.resolve()

    async def open(self, command: OpenTerminalCommand) -> TerminalAccess:
        task = await self._session.get(Task, command.task_id, with_for_update=True)
        if task is None:
            raise TerminalUnavailable("Task not found")
        if not task.manual_takeover:
            raise TerminalUnavailable("Take manual control before opening a terminal")
        if not task.workspace_path:
            raise TerminalUnavailable("Task has no prepared workspace")
        active_job = await self._session.scalar(
            select(Job.id).where(
                Job.task_id == task.id,
                Job.state.in_([JobState.CLAIMED, JobState.RUNNING]),
            )
        )
        if active_job:
            raise TerminalUnavailable(
                "The interrupted agent is still reaching a safe checkpoint; retry shortly"
            )
        workspace = Path(task.workspace_path).resolve()
        if not workspace.is_relative_to(self._workspace_root) or not workspace.is_dir():
            raise TerminalUnavailable("Task workspace is outside the managed workspace root")
        existing = await self._session.scalar(
            select(TerminalSession).where(
                TerminalSession.task_id == task.id, TerminalSession.status == "OPEN"
            )
        )
        if existing:
            existing.status = "REPLACED"
            existing.closed_at = datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        terminal = TerminalSession(
            task_id=task.id,
            node_id=command.node_id,
            token_hash=terminal_token_hash(token),
            cols=max(40, min(command.cols, 300)),
            rows=max(10, min(command.rows, 100)),
            expires_at=datetime.now(UTC) + timedelta(hours=4),
        )
        self._session.add(terminal)
        await self._session.commit()
        await self._session.refresh(terminal)
        return TerminalAccess(terminal.id, token, terminal.status, terminal.cols, terminal.rows)

    async def close(self, session_id: uuid.UUID) -> bool:
        terminal = await self._session.get(TerminalSession, session_id, with_for_update=True)
        if terminal is None:
            return False
        terminal.status = "CLOSED"
        terminal.closed_at = datetime.now(UTC)
        await self._session.commit()
        return True
