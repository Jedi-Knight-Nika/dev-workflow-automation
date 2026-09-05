import sys
import uuid
from pathlib import Path
from typing import Any, cast

import pytest

from app.domain.security import ActionRequest, Decision, ExecutionMode, TeamExecutionPolicy
from app.domain.security.paths import (
    WorkspaceEscapeError,
    resolve_workspace_path,
    windows_path_is_within,
)
from app.domain.security.policy import evaluate
from app.infrastructure.tools.gateway import GatewayContext, ToolGateway


class RecordingSession:
    def __init__(self) -> None:
        self.records: list[object] = []

    def add(self, record: object) -> None:
        self.records.append(record)

    async def commit(self) -> None:
        return None


def request(
    permission: str, *, command: tuple[str, ...] = (), branch: str | None = None
) -> ActionRequest:
    return ActionRequest(
        "shell",
        "push" if branch else "execute",
        permission,
        frozenset({permission}),
        command,
        branch,
        "agent/task-1",
    )


def test_autonomous_policy_allows_normal_engineering_commands() -> None:
    decision = evaluate(TeamExecutionPolicy(), request("RUN_TESTS", command=("npm", "test")))
    assert decision.decision == Decision.ALLOW


def test_conservative_policy_requires_approval_for_writes() -> None:
    policy = TeamExecutionPolicy(ExecutionMode.CONSERVATIVE)
    assert evaluate(policy, request("WRITE_REPOSITORY")).decision == Decision.REQUIRE_HUMAN


@pytest.mark.parametrize(
    "command", [("sudo", "shutdown"), ("docker", "run", "x"), ("mount", "/dev/x", "/x")]
)
def test_hard_denied_commands_cannot_be_enabled(command: tuple[str, ...]) -> None:
    assert (
        evaluate(TeamExecutionPolicy(), request("RUN_COMMANDS", command=command)).decision
        == Decision.DENY
    )


def test_missing_role_permission_is_denied() -> None:
    action = ActionRequest("filesystem", "write", "WRITE_REPOSITORY", frozenset())
    assert evaluate(TeamExecutionPolicy(), action).decision == Decision.DENY


def test_policy_rejects_unknown_capabilities() -> None:
    with pytest.raises(ValueError, match="Unknown capabilities"):
        TeamExecutionPolicy(settings={"MADE_UP_PERMISSION": Decision.ALLOW})


@pytest.mark.parametrize(
    ("timeout", "output"),
    [(9, 1_000_000), (7201, 1_000_000), (1200, 1023), (1200, 5_000_001)],
)
def test_policy_rejects_unsafe_runtime_limits(timeout: int, output: int) -> None:
    with pytest.raises(ValueError):
        TeamExecutionPolicy(
            max_command_timeout_seconds=timeout,
            max_output_bytes=output,
        )


def test_only_task_branch_can_be_pushed() -> None:
    assert (
        evaluate(TeamExecutionPolicy(), request("PUSH_TASK_BRANCH", branch="main")).decision
        == Decision.DENY
    )
    assert (
        evaluate(TeamExecutionPolicy(), request("PUSH_TASK_BRANCH", branch="agent/task-1")).decision
        == Decision.ALLOW
    )


def test_workspace_path_blocks_parent_and_sibling(tmp_path: Path) -> None:
    workspace = tmp_path / "task-1"
    workspace.mkdir()
    assert resolve_workspace_path(workspace, "src/file.py") == workspace / "src/file.py"
    with pytest.raises(WorkspaceEscapeError):
        resolve_workspace_path(workspace, "../task-2/secrets")


def test_workspace_path_blocks_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceEscapeError):
        resolve_workspace_path(workspace, "escape/secret")


def test_windows_ancestry_is_case_insensitive_and_not_prefix_based() -> None:
    assert windows_path_is_within(r"C:\work\task-1", r"SRC\file.py")
    assert not windows_path_is_within(r"C:\work\task-1", r"..\task-10\secret")
    assert not windows_path_is_within(r"C:\work\task-1", r"D:\secret")


@pytest.mark.asyncio
async def test_gateway_preserves_protected_environment(tmp_path: Path) -> None:
    session = RecordingSession()
    gateway = ToolGateway(
        cast(Any, session),
        GatewayContext(
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            None,
            None,
            tmp_path,
            "agent/task-1",
            frozenset({"RUN_COMMANDS"}),
        ),
        TeamExecutionPolicy(),
    )

    result = await gateway.run_command(
        [
            sys.executable,
            "-c",
            (
                "import os; print(os.environ['HOME']); print(os.environ['PATH']); "
                "print(os.environ['SAFE_VALUE'])"
            ),
        ],
        environment={"HOME": "/host/home", "PATH": "/untrusted", "SAFE_VALUE": "present"},
    )

    assert result.exit_code == 0
    assert str(tmp_path / ".worker-home") in result.stdout
    assert "/host/home" not in result.stdout
    assert "/untrusted" not in result.stdout
    assert "present" in result.stdout
    assert (tmp_path / ".worker-home").is_dir()
    assert session.records
