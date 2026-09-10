"""Cheap checkout checks before logging in or starting a native model turn."""

import os
from pathlib import Path

from app.agent_runtime.application.harness import WorkspaceUnavailable
from app.agent_runtime.infrastructure.process import capture


async def check_workspace(workspace: Path, *, read_only: bool = False) -> None:
    metadata = workspace / ".git"
    if metadata.is_symlink() or not metadata.is_dir():
        raise WorkspaceUnavailable("A standalone prepared Git checkout is required")
    mode = os.R_OK | os.X_OK | (0 if read_only else os.W_OK)
    if not os.access(workspace, mode) or not os.access(metadata, mode):
        raise WorkspaceUnavailable("The runner cannot access its task checkout metadata")
    try:
        root = await capture(
            (
                "git",
                "-c",
                "safe.directory=" + str(workspace.resolve()),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "rev-parse",
                "--show-toplevel",
            ),
            cwd=workspace,
            env={
                "PATH": os.defpath,
                "HOME": "/tmp",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0",
            },
            timeout=10,
        )
        if Path(os.fsdecode(root).strip()).resolve() != workspace.resolve():
            raise WorkspaceUnavailable("Git resolved outside the prepared task checkout")
    except (OSError, RuntimeError, TimeoutError) as exc:
        raise WorkspaceUnavailable(
            "Check task checkout ownership and Git metadata for runner UID 10001"
        ) from exc
