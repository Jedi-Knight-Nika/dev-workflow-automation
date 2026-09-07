import json
from pathlib import Path
from typing import Any

import pytest

from app.db.models import JobRole
from app.infrastructure.workers.repository_tools import REPOSITORY_TOOLS, RepositoryTools
from app.infrastructure.workers.structured_output import (
    ProviderRunInterrupted,
    run_with_structured_repair,
)
from app.providers.base import AIProvider, ProviderModel, ProviderRequest, ProviderResponse
from app.providers.http import OpenAIProvider


@pytest.mark.asyncio
async def test_live_reads_are_bounded_and_reject_secrets_and_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "module.py").write_text("value = 1\n")
    (tmp_path / ".env").write_text("SECRET=never-read")
    (tmp_path / "alias.py").symlink_to(tmp_path / ".env")

    async def git(*args: str, **kwargs: Any) -> str:
        return "module.py\n.env\nalias.py"

    monkeypatch.setattr("app.infrastructure.workers.repository_tools.run_git", git)
    monkeypatch.setattr("app.infrastructure.workers.executor.run_git", git)
    tools = RepositoryTools([(".", tmp_path)], max_calls=4, max_bytes=12)
    listed = json.loads(await tools.execute("list_repository_files", '{"pattern":"*","offset":0}'))
    assert ".env" not in listed["paths"]
    blocked = await tools.execute("read_repository_files", '{"paths":[".env"]}')
    assert "error" in json.loads(blocked) and "never-read" not in blocked
    result = json.loads(
        await tools.execute("read_repository_files", '{"paths":["module.py","alias.py"]}')
    )
    assert result[0]["content"] == "value = 1\n"
    assert result[1]["status"] == "NOT_READABLE"
    assert (
        json.loads(await tools.execute("read_repository_files", '{"paths":["module.py"]}'))[0][
            "status"
        ]
        == "ALREADY_READ"
    )
    with pytest.raises(RuntimeError, match="budget"):
        await tools.execute("list_repository_files", "{}")


class ToolProvider(AIProvider):
    supports_repository_tools = True

    def __init__(self, outputs: list[ProviderResponse]) -> None:
        super().__init__("test")
        self.outputs = outputs
        self.requests: list[ProviderRequest] = []

    async def run(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return self.outputs.pop(0)

    async def list_models(self) -> list[ProviderModel]:
        return []


@pytest.mark.asyncio
async def test_final_turn_retains_evidence_and_disables_tools() -> None:
    call = {
        "type": "function_call",
        "name": "list_repository_files",
        "call_id": "last-read",
        "arguments": '{"pattern":"*","offset":0}',
    }
    provider = ToolProvider(
        [
            ProviderResponse(
                "", tool_calls=(call,), continuation=(call,), input_tokens=10, output_tokens=2
            ),
            ProviderResponse(
                '{"result":"PLAN_READY","goal":"Fix","ordered_steps":["Edit"],"acceptance_criteria":["Pass"]}',
                input_tokens=20,
                output_tokens=10,
            ),
        ]
    )
    result, attempts = await run_with_structured_repair(
        provider,
        ProviderRequest(model="test", system="plan", prompt="task", tools=REPOSITORY_TOOLS),
        JobRole.THINKER,
        repository_tools=RepositoryTools([], max_calls=20),
        max_model_calls=2,
    )
    assert result["result"] == "PLAN_READY" and len(attempts) == 2
    final = provider.requests[-1]
    assert not final.allow_tool_calls
    payload = OpenAIProvider._payload(final)
    assert payload["tool_choice"] == "none"
    assert payload["input"][1]["call_id"] == "last-read"
    assert payload["input"][2]["type"] == "function_call_output"


@pytest.mark.asyncio
async def test_zero_model_budget_never_contacts_provider() -> None:
    provider = ToolProvider([])
    with pytest.raises(RuntimeError, match="Model-turn budget exhausted"):
        await run_with_structured_repair(
            provider,
            ProviderRequest(model="test", system="plan", prompt="task"),
            JobRole.THINKER,
            max_model_calls=0,
        )
    assert provider.requests == []


@pytest.mark.asyncio
async def test_native_tool_loop_replays_reasoning_and_accounts_every_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call = {
        "type": "function_call",
        "name": "list_repository_files",
        "call_id": "call-1",
        "arguments": '{"pattern":"*","offset":0}',
    }
    reasoning = {"type": "reasoning", "id": "r1", "encrypted_content": "opaque"}
    provider = ToolProvider(
        [
            ProviderResponse(
                text="",
                input_tokens=10,
                output_tokens=2,
                tool_calls=(call,),
                continuation=(reasoning, call),
            ),
            ProviderResponse(
                text='{"result":"IMPLEMENTED","summary":"No changes required"}',
                input_tokens=20,
                output_tokens=8,
            ),
        ]
    )

    async def git(*args: str, **kwargs: Any) -> str:
        return "module.py"

    monkeypatch.setattr("app.infrastructure.workers.repository_tools.run_git", git)
    checks: list[int] = []

    async def budget(attempts: list) -> None:
        checks.append(len(attempts))

    result, attempts = await run_with_structured_repair(
        provider,
        ProviderRequest(model="test", system="system", prompt="task", tools=REPOSITORY_TOOLS),
        JobRole.EXECUTOR,
        before_attempt=budget,
        repository_tools=RepositoryTools([(".", tmp_path)], max_calls=3),
    )
    assert result["result"] == "IMPLEMENTED"
    assert len(attempts) == 2 and checks == [0, 1]
    history = provider.requests[1].tool_history
    assert history[:2] == (reasoning, call)
    assert history[2]["call_id"] == "call-1"
    payload = OpenAIProvider._payload(provider.requests[1])
    assert payload["store"] is False and payload["parallel_tool_calls"] is False
    assert payload["input"][1:] == list(history)


@pytest.mark.asyncio
async def test_question_ends_model_turn_and_restricts_recipients() -> None:
    call = {
        "type": "function_call",
        "name": "ask_agent",
        "call_id": "q1",
        "arguments": '{"target_node_id":"planner","question":"Which invariant applies?"}',
    }
    provider = ToolProvider([ProviderResponse(text="", tool_calls=(call,), continuation=(call,))])
    result, attempts = await run_with_structured_repair(
        provider,
        ProviderRequest(model="test", system="system", prompt="task"),
        JobRole.EXECUTOR,
        repository_tools=RepositoryTools([], max_calls=2, consultants={"planner"}),
    )
    assert result == {
        "result": "CONSULTATION_REQUESTED",
        "target_node_id": "planner",
        "question": "Which invariant applies?",
    }
    assert len(attempts) == 1
    denied = await RepositoryTools([], 2).execute("ask_agent", call["arguments"])
    assert "error" in json.loads(denied)


@pytest.mark.asyncio
async def test_provider_outage_retains_paid_attempts_and_original_failure() -> None:
    call = {
        "type": "function_call",
        "name": "list_repository_files",
        "call_id": "one",
        "arguments": '{"pattern":"*","offset":0}',
    }

    class OutageProvider(ToolProvider):
        async def run(self, request: ProviderRequest) -> ProviderResponse:
            if self.requests:
                raise RuntimeError("PROVIDER_UNAVAILABLE: transport failed")
            return await super().run(request)

    provider = OutageProvider(
        [
            ProviderResponse(
                text="",
                input_tokens=100,
                output_tokens=10,
                tool_calls=(call,),
                continuation=(call,),
            )
        ]
    )
    with pytest.raises(ProviderRunInterrupted) as error:
        await run_with_structured_repair(
            provider,
            ProviderRequest(model="test", system="system", prompt="task"),
            JobRole.EXECUTOR,
            repository_tools=RepositoryTools([], 2),
        )
    assert len(error.value.attempts) == 1
    assert error.value.attempts[0].response.input_tokens == 100
    assert "PROVIDER_UNAVAILABLE" in str(error.value.cause)
