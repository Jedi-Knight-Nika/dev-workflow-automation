import asyncio
import fcntl
import os
import pty
import re
import signal
import struct
import subprocess
import termios
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi import WebSocket
from sqlalchemy import func, select

from app.db.models import Task, TerminalEvent, TerminalSession
from app.db.session import SessionLocal
from app.infrastructure.persistence.terminal_sessions import terminal_token_hash

SECRET_PATTERN = re.compile(r"(?i)(token|secret|password|api[_-]?key)(\s*[=:]\s*)([^\s]+)")


def scrub_terminal_output(value: str) -> str:
    return SECRET_PATTERN.sub(r"\1\2[REDACTED]", value)


@dataclass(slots=True)
class LiveTerminal:
    process: subprocess.Popen[bytes]
    master_fd: int
    subscribers: set[WebSocket] = field(default_factory=set)
    reader_task: asyncio.Task[None] | None = None
    history: str = ""


class LocalPtyTerminalRuntime:
    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, LiveTerminal] = {}
        self._locks: dict[uuid.UUID, asyncio.Lock] = {}

    async def attach(self, session_id: uuid.UUID, token: str, websocket: WebSocket) -> None:
        terminal, workspace = await self._authorize(session_id, token)
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            live = self._sessions.get(session_id)
            if live is None or live.process.poll() is not None:
                live = self._start(terminal, workspace)
                self._sessions[session_id] = live
                live.reader_task = asyncio.create_task(self._read_output(session_id, live))
            live.subscribers.add(websocket)
        await websocket.accept()
        if live.history:
            await websocket.send_json({"type": "output", "data": live.history})
        await websocket.send_json({"type": "status", "status": "CONNECTED"})
        try:
            while True:
                message = await websocket.receive_json()
                kind = message.get("type")
                if kind == "input":
                    data = str(message.get("data", ""))[:65_536]
                    os.write(live.master_fd, data.encode())
                    await self._audit(session_id, "INPUT", {"bytes": len(data.encode())})
                elif kind == "resize":
                    self._resize(
                        live.master_fd,
                        int(message.get("rows", terminal.rows)),
                        int(message.get("cols", terminal.cols)),
                    )
                elif kind == "interrupt":
                    os.killpg(live.process.pid, signal.SIGINT)
                    await self._audit(session_id, "INTERRUPTED", {})
                elif kind == "terminate":
                    os.killpg(live.process.pid, signal.SIGTERM)
                    await self._audit(session_id, "TERMINATED", {})
        finally:
            live.subscribers.discard(websocket)

    async def _authorize(self, session_id: uuid.UUID, token: str) -> tuple[TerminalSession, Path]:
        async with SessionLocal() as session:
            terminal = await session.get(TerminalSession, session_id)
            if (
                terminal is None
                or terminal.status != "OPEN"
                or terminal.expires_at < datetime.now(UTC)
                or terminal.token_hash != terminal_token_hash(token)
            ):
                raise PermissionError("Terminal session is invalid or expired")
            task = await session.get(Task, terminal.task_id)
            if task is None or not task.manual_takeover or not task.workspace_path:
                raise PermissionError("Task is not under manual control")
            return terminal, Path(task.workspace_path)

    def _start(self, terminal: TerminalSession, workspace: Path) -> LiveTerminal:
        master_fd, slave_fd = pty.openpty()
        self._resize(master_fd, terminal.rows, terminal.cols)
        environment = {
            "HOME": "/tmp/terminal-home",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "LANG": "C.UTF-8",
        }
        Path(environment["HOME"]).mkdir(mode=0o700, parents=True, exist_ok=True)
        process = subprocess.Popen(
            ["/bin/bash", "--noprofile", "--norc"],
            cwd=workspace,
            env=environment,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
        )
        os.close(slave_fd)
        os.set_blocking(master_fd, False)
        return LiveTerminal(process, master_fd)

    async def _read_output(self, session_id: uuid.UUID, live: LiveTerminal) -> None:
        while live.process.poll() is None:
            try:
                data = await asyncio.to_thread(os.read, live.master_fd, 16_384)
            except (BlockingIOError, OSError):
                await asyncio.sleep(0.02)
                continue
            if not data:
                await asyncio.sleep(0.02)
                continue
            output = scrub_terminal_output(data.decode(errors="replace"))
            live.history = (live.history + output)[-1_000_000:]
            for websocket in tuple(live.subscribers):
                try:
                    await websocket.send_json({"type": "output", "data": output})
                except RuntimeError:
                    live.subscribers.discard(websocket)
            await self._audit(session_id, "OUTPUT", {"data": output[-16_384:]})
        exit_code = live.process.returncode
        await self._audit(session_id, "EXIT", {"exit_code": exit_code})
        async with SessionLocal() as session:
            terminal = await session.get(TerminalSession, session_id)
            if terminal:
                terminal.status = "EXITED"
                terminal.exit_code = exit_code
                terminal.closed_at = datetime.now(UTC)
                await session.commit()

    async def _audit(
        self, session_id: uuid.UUID, event_type: str, payload: dict[str, object]
    ) -> None:
        async with SessionLocal() as session:
            sequence = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(TerminalEvent.sequence), 0)).where(
                            TerminalEvent.session_id == session_id
                        )
                    )
                    or 0
                )
                + 1
            )
            session.add(
                TerminalEvent(
                    session_id=session_id,
                    sequence=sequence,
                    event_type=event_type,
                    payload=payload,
                )
            )
            await session.commit()

    @staticmethod
    def _resize(fd: int, rows: int, cols: int) -> None:
        size = struct.pack("HHHH", max(10, min(rows, 100)), max(40, min(cols, 300)), 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, size)


terminal_runtime = LocalPtyTerminalRuntime()
