import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.db.models import JobRole
from app.domain.security import TeamExecutionPolicy
from app.infrastructure.tools.gateway import (
    GatewayContext,
    ToolGateway,
    ToolNeedsApproval,
    ToolOperationError,
)
from app.infrastructure.workers.executor_tools import (
    EXECUTOR_TOOLS,
    ExecutorTools,
    InteractiveExecutorProposal,
)
from app.infrastructure.workers.structured_output import run_with_structured_repair
from app.providers.base import AIProvider, ProviderModel, ProviderRequest, ProviderResponse


class Session:
    def add(self, record: object) -> None:
        pass

    async def commit(self) -> None:
        pass


def gateway(root: Path, permissions: frozenset[str] | None = None) -> ToolGateway:
    return ToolGateway(
        Session(),  # type: ignore[arg-type]
        GatewayContext(
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            None,
            None,
            root,
            "agent/test",
            permissions
            if permissions is not None
            else frozenset(
                {
                    "READ_REPOSITORY",
                    "WRITE_REPOSITORY",
                    "CREATE_FILES",
                    "DELETE_FILES",
                    "RUN_COMMANDS",
                    "RUN_TESTS",
                    "RUN_LINTER",
                }
            ),
            50,
        ),
        TeamExecutionPolicy(),
    )


def executor(root: Path, **kwargs: Any) -> ExecutorTools:
    return ExecutorTools([(".", root)], 40, gateways={".": gateway(root)}, **kwargs)


async def invoke(tools: ExecutorTools, name: str, **args: Any) -> Any:
    return json.loads(await tools.execute(name, json.dumps({"repository": ".", **args})))


class ScriptedProvider(AIProvider):
    supports_repository_tools = True

    def __init__(self, steps: list[tuple[str, dict[str, Any]]]) -> None:
        super().__init__("test")
        self.steps = steps
        self.requests: list[ProviderRequest] = []

    async def run(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if not self.steps:
            return ProviderResponse(
                '{"result":"IMPLEMENTED","summary":"Fixed and tested"}',
                input_tokens=10,
                output_tokens=10,
            )
        name, args = self.steps.pop(0)
        call = {
            "type": "function_call",
            "name": name,
            "call_id": str(len(self.requests)),
            "arguments": json.dumps({"repository": ".", **args}),
        }
        return ProviderResponse(
            "", tool_calls=(call,), continuation=(call,), input_tokens=10, output_tokens=10
        )

    async def list_models(self) -> list[ProviderModel]:
        return []


@pytest.mark.asyncio
async def test_edit_failure_and_test_failure_are_corrected_in_same_model_loop(
    tmp_path: Path,
) -> None:
    (tmp_path / "value.py").write_text("value = 1\n")
    command = {
        "command": [sys.executable, "-c", "from value import value; assert value == 2"],
        "directory": ".",
        "timeout_seconds": 10,
    }
    provider = ScriptedProvider(
        [
            ("read_workspace_file", {"path": "value.py"}),
            ("edit_workspace_file", {"path": "value.py", "old_text": "missing", "new_text": "2"}),
            ("run_workspace_command", command),
            (
                "edit_workspace_file",
                {"path": "value.py", "old_text": "value = 1", "new_text": "value = 2"},
            ),
            (
                "run_workspace_command",
                {
                    **command,
                    "command": [
                        sys.executable,
                        "-c",
                        "exec(open('value.py').read()); assert value == 2",
                    ],
                },
            ),
        ]
    )
    result, attempts = await run_with_structured_repair(
        provider,
        ProviderRequest(model="test", system="implement", prompt="task", tools=EXECUTOR_TOOLS),
        JobRole.EXECUTOR,
        repository_tools=executor(tmp_path),
        response_model=InteractiveExecutorProposal,
        max_model_calls=8,
    )
    assert result["result"] == "IMPLEMENTED" and result["patches"] == []
    assert (tmp_path / "value.py").read_text() == "value = 2\n"
    assert len(attempts) == 6
    outputs = [
        json.loads(item["output"])
        for item in provider.requests[-1].tool_history
        if item["type"] == "function_call_output"
    ]
    assert outputs[1]["status"] == "ERROR" and outputs[1]["correctable"]
    assert outputs[2]["exit_code"] != 0 and "AssertionError" in outputs[2]["stderr"]
    assert outputs[3]["status"] == "APPLIED" and outputs[4]["exit_code"] == 0


@pytest.mark.asyncio
async def test_new_files_are_readable_and_edits_do_not_reset_budgets(tmp_path: Path) -> None:
    tools = executor(tmp_path, max_bytes=10)
    assert (
        await invoke(tools, "edit_workspace_file", path="new.txt", old_text="", new_text="hello")
    )["status"] == "APPLIED"
    assert (await invoke(tools, "read_workspace_file", path="new.txt"))["content"] == "hello"
    assert (
        await invoke(
            tools, "edit_workspace_file", path="new.txt", old_text="hello", new_text="world"
        )
    )["status"] == "APPLIED"
    assert tools.remaining == 5 and tools.calls == 3
    assert (await invoke(tools, "read_workspace_file", path="new.txt"))["content"] == "world"
    assert (await invoke(tools, "read_workspace_file", path="new.txt"))["status"] == "ERROR"


@pytest.mark.asyncio
async def test_secret_symlinks_traversal_and_unknown_repository_rejected(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("secret content")
    (tmp_path / "alias").symlink_to(tmp_path / ".env")
    tools = executor(tmp_path)
    for path in ["../outside", ".env", "alias"]:
        result = await invoke(tools, "edit_workspace_file", path=path, old_text="", new_text="bad")
        assert result["status"] == "ERROR"
    result = json.loads(
        await tools.execute("read_workspace_file", '{"repository":"other","path":"alias"}')
    )
    assert result["status"] == "ERROR"
    assert (tmp_path / ".env").read_text() == "secret content"


@pytest.mark.asyncio
async def test_commands_require_permission_and_confined_working_directory(tmp_path: Path) -> None:
    tools = ExecutorTools([(".", tmp_path)], 10, gateways={".": gateway(tmp_path, frozenset())})
    args = {
        "command": [sys.executable, "-c", "print('ok')"],
        "directory": ".",
        "timeout_seconds": 10,
    }
    denied = await invoke(tools, "run_workspace_command", **args)
    assert denied["status"] == "ERROR" and not denied["correctable"]
    tools = executor(tmp_path)
    assert (await invoke(tools, "run_workspace_command", **{**args, "directory": ".."}))[
        "status"
    ] == "ERROR"
    (tmp_path / "frontend").mkdir()
    outcome = await invoke(
        tools,
        "run_workspace_command",
        **{
            **args,
            "directory": "frontend",
            "command": [sys.executable, "-c", "import os; print(os.getcwd())"],
        },
    )
    assert outcome["exit_code"] == 0 and str(tmp_path / "frontend") in outcome["stdout"]


@pytest.mark.asyncio
async def test_detected_checks_run_in_subdirectory_and_register_final_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "backend").mkdir()
    monkeypatch.setattr(
        "app.infrastructure.workers.executor.dependency_setup_commands", lambda _: []
    )
    monkeypatch.setattr(
        "app.infrastructure.workers.executor.detected_checks",
        lambda _: [[sys.executable, "-c", "import os; assert os.getcwd().endswith('/backend')"]],
    )
    tools = executor(tmp_path)
    result = await invoke(tools, "run_workspace_checks", directory="backend")
    assert result["passed"] and tools.validation_directories == {".": {"backend"}}


@pytest.mark.asyncio
async def test_policy_approval_stops_loop_before_another_paid_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approval = uuid.uuid4()

    async def require_approval(*args: Any, **kwargs: Any) -> None:
        raise ToolNeedsApproval(approval)

    monkeypatch.setattr(ToolGateway, "write_file", require_approval)
    provider = ScriptedProvider(
        [("edit_workspace_file", {"path": "new.txt", "old_text": "", "new_text": "data"})]
    )
    result, attempts = await run_with_structured_repair(
        provider,
        ProviderRequest(model="test", system="implement", prompt="task", tools=EXECUTOR_TOOLS),
        JobRole.EXECUTOR,
        repository_tools=executor(tmp_path),
        response_model=InteractiveExecutorProposal,
        max_model_calls=8,
    )
    assert result["result"] == "NEEDS_HUMAN" and str(approval) in result["reason"]
    InteractiveExecutorProposal.model_validate(result)
    assert len(attempts) == 1 and not (tmp_path / "new.txt").exists()


@pytest.mark.asyncio
async def test_cancellation_terminates_running_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cancelled = False
    terminated = asyncio.Event()
    original = ToolGateway._terminate_tree

    async def terminate(self: ToolGateway, pid: int) -> None:
        await original(pid)
        terminated.set()

    async def check() -> bool:
        return cancelled

    monkeypatch.setattr(ToolGateway, "_terminate_tree", terminate)
    tools = executor(tmp_path, is_cancelled=check)
    task = asyncio.create_task(
        invoke(
            tools,
            "run_workspace_command",
            command=[sys.executable, "-c", "import time; time.sleep(30)"],
            directory=".",
            timeout_seconds=60,
        )
    )
    await asyncio.sleep(0.1)
    cancelled = True
    with pytest.raises(RuntimeError, match="cancelled"):
        await asyncio.wait_for(task, 8)
    assert terminated.is_set()


@pytest.mark.asyncio
async def test_bad_patch_is_operation_error_not_permission_denial(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("old\n")
    with pytest.raises(ToolOperationError, match="Patch did not apply"):
        await gateway(tmp_path).apply_patch(
            "file.txt", "--- a/file.txt\n+++ b/file.txt\n@@ -1,8 +1,8 @@\n-old\n+new\n"
        )
    assert (tmp_path / "file.txt").read_text() == "old\n"


def test_interactive_final_cannot_apply_edits_twice() -> None:
    with pytest.raises(ValidationError, match="already|twice"):
        InteractiveExecutorProposal.model_validate(
            {"result": "IMPLEMENTED", "summary": "done", "files": [{"path": "x", "content": "x"}]}
        )
