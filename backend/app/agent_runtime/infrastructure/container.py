from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class RunnerMounts:
    task_id: UUID
    workspace: Path
    state: Path
    manifest: Path
    tasks_root: Path
    state_root: Path
    control_root: Path
    state_namespace: UUID | None = None

    @property
    def lock_path(self) -> Path:
        return self.control_root / str(self.task_id) / "workspace.lock"

    def validate(self) -> None:
        task_root = (self.tasks_root / str(self.task_id)).resolve()
        state_root = (self.state_root / str(self.task_id)).resolve()
        if (
            task_root.parent != self.tasks_root.resolve()
            or state_root.parent != self.state_root.resolve()
        ):
            raise ValueError("Task roots cannot be symlinks outside their storage root")
        for path in (
            self.workspace,
            self.state,
            self.manifest,
            self.tasks_root,
            self.state_root,
            self.control_root,
        ):
            if not path.is_absolute():
                raise ValueError("Runner mounts must use absolute paths")
        if task_root == Path("/") or state_root == Path("/"):
            raise ValueError("Broad mounts are forbidden")
        if not self.workspace.resolve().is_relative_to(task_root):
            raise ValueError("Only this task's checkout can be mounted")
        expected_state = (
            state_root / "helpers" / str(self.state_namespace)
            if self.state_namespace
            else state_root
        )
        if self.state.resolve() != expected_state:
            raise ValueError("Harness state must be isolated by task ID")
        control = self.control_root.resolve() / str(self.task_id)
        if not self.manifest.resolve().is_relative_to(control):
            raise ValueError("Manifest must belong to this task's controller directory")
        if (
            self.lock_path.is_symlink()
            or not self.lock_path.is_file()
            or self.lock_path.resolve().parent != control
        ):
            raise ValueError("A controller-owned task workspace lock is required")
        if self.manifest.resolve().is_relative_to(
            self.state.resolve()
        ) or self.manifest.resolve().is_relative_to(self.workspace.resolve()):
            raise ValueError("Runner must not be able to write its own controller authorization")
        if self.workspace.resolve().is_relative_to(self.state.resolve()):
            raise ValueError("Source and native harness state must be separate")
        if not self.workspace.is_dir() or not self.state.is_dir() or not self.manifest.is_file():
            raise ValueError("Prepare and verify all runner mounts before launch")
        if (self.workspace / ".git").is_file():
            raise ValueError("Linked worktrees require an explicitly isolated Git directory")


def developer_container_spec(
    mounts: RunnerMounts,
    *,
    image: str,
    network: str,
    provider_environment: dict[str, str],
    read_only: bool = False,
) -> dict[str, Any]:
    mounts.validate()
    if mounts.state_namespace and not read_only:
        raise ValueError("Helper workspaces must be read-only")
    if network in {"host", "bridge", "none", "default", ""}:
        raise ValueError("An explicitly isolated provider-egress network is required")
    allowed = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}
    if set(provider_environment) - allowed:
        raise ValueError("Runner must not receive database, GitHub or host credentials")
    return {
        "Image": image,
        "User": "10001:10001",
        "WorkingDir": "/workspace",
        "Cmd": [
            "/app/.venv/bin/python",
            "-m",
            "app.agent_runtime.infrastructure.runner",
            "/run/control/task.json",
        ],
        "Env": [f"{key}={value}" for key, value in sorted(provider_environment.items())],
        "AttachStdout": True,
        "AttachStderr": True,
        "Labels": {"managed_by": "engineering-scheduler", "task_id": str(mounts.task_id)},
        "HostConfig": {
            "AutoRemove": False,
            "ReadonlyRootfs": True,
            "Privileged": False,
            "Binds": [
                f"{mounts.workspace}:/workspace:{'ro' if read_only else 'rw'}",
                f"{mounts.state}:/home/runner:rw",
                f"{mounts.manifest.parent}:/run/control:ro",
                f"{mounts.lock_path}:/run/workspace.lock:ro",
            ],
            "NetworkMode": network,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=512m"},
            "PidsLimit": 256,
            "Memory": 2 * 1024**3,
            "NanoCpus": 2_000_000_000,
            "Init": True,
        },
    }


def validation_container_spec(mounts: RunnerMounts, *, image: str) -> dict[str, Any]:
    """Repository tests cannot access native session state or provider secrets."""
    spec = developer_container_spec(
        mounts, image=image, network="validation-isolated", provider_environment={}
    )
    spec["HostConfig"]["NetworkMode"] = "none"
    spec["HostConfig"]["Binds"] = [
        value for value in spec["HostConfig"]["Binds"] if ":/home/runner:" not in value
    ]
    spec["HostConfig"]["Tmpfs"]["/home/runner"] = (
        "rw,nosuid,nodev,size=128m,uid=10001,gid=10001,mode=0700"
    )
    spec["Env"] = [
        "HOME=/home/runner",
        "GIT_CONFIG_NOSYSTEM=1",
        "GIT_CONFIG_GLOBAL=/dev/null",
        "GIT_TERMINAL_PROMPT=0",
    ]
    spec["Cmd"] = [
        "/app/.venv/bin/python",
        "-m",
        "app.engineering.infrastructure.validator_runner",
    ]
    return spec
