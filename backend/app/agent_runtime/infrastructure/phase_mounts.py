"""Task runner mount preparation shared by execution and delivery phases."""

from pathlib import Path

from app.agent_runtime.infrastructure.container import RunnerMounts
from app.agent_runtime.infrastructure.models import DeveloperSession
from app.engineering.application.jobs import PhaseLease
from app.platform.configuration.settings import Settings


def phase_mounts(
    settings: Settings,
    lease: PhaseLease,
    native: DeveloperSession,
    *,
    compaction: bool = False,
    continuity: bool = False,
) -> RunnerMounts:
    root = settings.harness_control_root.resolve()
    directory = (
        root
        / str(lease.task_id)
        / (str(lease.token) + ("-compact" if compaction else "-ack" if continuity else ""))
    )
    directory.mkdir(parents=True, exist_ok=False)
    lock_path = root / str(lease.task_id) / "workspace.lock"
    try:
        lock_path.touch(exist_ok=False)
    except FileExistsError:
        pass  # Never replace an inode a surviving runner may still have locked.
    return RunnerMounts(
        lease.task_id,
        Path(native.workspace_path),
        Path(native.state_path),
        directory / "task.json",
        settings.workspace_root.resolve() / "tasks",
        settings.harness_state_root.resolve(),
        root,
    )
