import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.db.models import Job, JobRole, Task
from app.infrastructure.workers.context_compiler import ContextCompiler
from app.infrastructure.workers.context_efficiency import (
    compact_checks,
    request_token_reserve,
    source_map,
)
from app.infrastructure.workers.repository_tools import RepositoryTools
from app.providers.base import ProviderRequest
from app.providers.http import OpenAIProvider
from app.worker import BudgetExceeded, enforce_spending_budget


def test_current_source_map_prefers_explicit_plan_paths_and_excludes_secrets():
    manifest = "\n".join(
        [".env", "backend/app/teams.py", "frontend/package.json"]
        + [f"other/file{i}.py" for i in range(2000)]
    )
    result = source_map(manifest, "Update backend/app/teams.py; other implementation files later")
    assert result["candidate_paths"][0] == "backend/app/teams.py"
    assert ".env" not in json.dumps(result)
    assert len(json.dumps(result)) < 6000


def test_checks_preserve_outcomes_without_repeating_success_logs():
    checks = [
        {"name": "pass", "passed": True, "output": "ok" * 5000},
        {"name": "fail", "passed": False, "output": "noise" * 5000 + "AssertionError"},
    ]
    result = compact_checks(checks)
    assert len(result) == 2 and result[1]["passed"] is False
    assert result[1]["output"].endswith("AssertionError")
    assert len(json.dumps(result)) < 2500
    assert checks[0]["output"] == "ok" * 5000


def test_batching_is_explicit_and_preserved_in_payload():
    request = ProviderRequest(
        "test",
        "system",
        "task",
        tools=({"name": "read", "parameters": {}},),
        parallel_tool_calls=True,
    )
    assert OpenAIProvider._payload(request)["parallel_tool_calls"] is True


def test_request_reserve_includes_history_schema_and_output():
    base = ProviderRequest("test", "system", "task", max_output_tokens=500)
    large = ProviderRequest(
        "test",
        "system",
        "task",
        max_output_tokens=500,
        tool_history=({"output": "ა" * 10000},),
        response_schema={"description": "a" * 1000},
    )
    assert request_token_reserve(large) > request_token_reserve(base) + 10000
    assert request_token_reserve(base) >= 500


@pytest.mark.asyncio
async def test_next_request_is_rejected_before_budget_overshoot():
    session = AsyncMock()
    session.get.return_value = None
    session.execute.return_value = SimpleNamespace(one=lambda: (84000, 0, 6))
    job = Job(id=uuid.uuid4(), task_id=uuid.uuid4(), role=JobRole.EXECUTOR)
    task = Task(id=job.task_id, team_id=None)
    with pytest.raises(BudgetExceeded, match="request was not sent"):
        await enforce_spending_budget(
            session, job, task, Settings(_env_file=None), {}, [], reserved_tokens=40000
        )


@pytest.mark.asyncio
async def test_source_range_batch_shares_output_allowance(tmp_path: Path, monkeypatch):
    (tmp_path / "large.py").write_text("value = 1\n" * 2000)
    monkeypatch.setattr(
        "app.infrastructure.workers.repository_tools.run_git", AsyncMock(return_value="large.py")
    )
    tools = RepositoryTools([(".", tmp_path)], 30, max_bytes=100000)
    args = json.dumps(
        {
            "ranges": [
                {"path": "large.py", "start_line": i * 200 + 1, "end_line": i * 200 + 200}
                for i in range(10)
            ]
        }
    )
    rows = json.loads(await tools.execute("read_repository_ranges", args))
    assert sum(len(row.get("content", "").encode()) for row in rows) <= 8000
    assert any(row["next_line"] for row in rows)
    assert tools.remaining >= 92000
    tools.begin_turn()
    assert tools.read_allowance == 8000


@pytest.mark.asyncio
async def test_full_file_batch_cannot_dump_95kb(tmp_path: Path, monkeypatch):
    paths = [f"module{i}.py" for i in range(20)]
    for path in paths:
        (tmp_path / path).write_text("value = 1\n" * 500)
    monkeypatch.setattr(
        "app.infrastructure.workers.executor.run_git", AsyncMock(return_value="\n".join(paths))
    )
    tools = RepositoryTools([(".", tmp_path)], 30, max_bytes=100000)
    result = json.loads(await tools.execute("read_repository_files", json.dumps({"paths": paths})))
    assert sum(len(r.get("content", "").encode()) for r in result) <= 8000
    assert any(r["status"] == "CONTEXT_LIMIT" for r in result)


@pytest.mark.asyncio
async def test_native_executor_gets_live_paths_without_bulk_files_or_rag(monkeypatch):
    compiler = ContextCompiler(AsyncMock(), native_repository_tools=True)
    monkeypatch.setattr(compiler, "_base", lambda *_: {"task": {"title": "Team setting"}})
    for method, value in [
        ("_include_conversation", None),
        ("_persistent_memory", {}),
        ("_previous_checkpoint", None),
        ("latest_plan", {"data": {"targets": ["backend/teams.py"]}}),
        ("_findings", []),
        ("_knowledge", []),
    ]:
        monkeypatch.setattr(compiler, method, AsyncMock(return_value=value))
    monkeypatch.setattr(
        compiler, "_finish", AsyncMock(side_effect=lambda task, job, context, started: context)
    )
    monkeypatch.setattr(
        "app.infrastructure.workers.context_compiler.run_git",
        AsyncMock(return_value="backend/teams.py"),
    )
    bulk = AsyncMock(side_effect=AssertionError("must not load bulk source"))
    monkeypatch.setattr("app.infrastructure.workers.context_compiler.repository_context", bulk)
    item = SimpleNamespace(
        path=Path("/tmp/repo"),
        repository=SimpleNamespace(id=uuid.uuid4(), owner="owner", name="repo"),
        scope=SimpleNamespace(branch_name="branch", base_revision="a", current_revision="b"),
    )
    result = await compiler.compile_for_scoped_executor(
        SimpleNamespace(workspace_path="/tmp/repo"), SimpleNamespace(), [item]
    )
    assert result["repositories"][0]["source_map"]["candidate_paths"] == ["backend/teams.py"]
    assert result["repositories"][0]["retrieved_knowledge"] == []
    bulk.assert_not_called()
    assert compiler._knowledge.await_count == 1


@pytest.mark.asyncio
async def test_single_repository_routing_does_not_embed_source(monkeypatch):
    compiler = ContextCompiler(AsyncMock())
    monkeypatch.setattr(compiler, "_base", lambda *_: {})
    monkeypatch.setattr(compiler, "_include_conversation", AsyncMock())
    monkeypatch.setattr(compiler, "_persistent_memory", AsyncMock(return_value={}))
    monkeypatch.setattr(compiler, "_knowledge", AsyncMock(return_value=[]))
    retrieval = AsyncMock(side_effect=AssertionError("no routing embedding required"))
    monkeypatch.setattr(compiler, "_intake_knowledge", retrieval)
    repo = SimpleNamespace(
        id=uuid.uuid4(),
        provider="github",
        owner="owner",
        name="repo",
        default_branch="main",
        index_status=SimpleNamespace(value="READY"),
        latest_sha="a",
        indexed_sha="a",
    )
    monkeypatch.setattr(compiler, "_team_repositories", AsyncMock(return_value=[repo]))
    monkeypatch.setattr(
        compiler, "_finish", AsyncMock(side_effect=lambda task, job, context, started: context)
    )
    result = await compiler.compile_for_deliverer(
        SimpleNamespace(), SimpleNamespace(payload={}, action="INTERPRET_TASK")
    )
    assert len(result["repository_candidates"]) == 1
    retrieval.assert_not_called()
