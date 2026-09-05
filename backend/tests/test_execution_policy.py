from pathlib import Path

import pytest

from app.domain.security import ActionRequest, Decision, ExecutionMode, TeamExecutionPolicy
from app.domain.security.paths import (
    WorkspaceEscapeError,
    resolve_workspace_path,
    windows_path_is_within,
)
from app.domain.security.policy import evaluate


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
