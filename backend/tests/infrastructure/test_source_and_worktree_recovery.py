import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.models import Task
from app.infrastructure.git.workspaces import add_task_worktree, run_git, task_branch
from app.infrastructure.workers.context_compiler import ContextCompiler
from app.infrastructure.workers.repository_tools import RepositoryTools
from app.providers.base import ProviderRequest
from app.providers.http import OpenAIProvider
from app.providers.streaming import normalize_stream_event


async def repository(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "test@example.invalid")
    await run_git("init", "-b", "main", str(root))
    (root / "source.py").write_text("value = 1\n")
    await run_git("add", "source.py", cwd=root)
    await run_git("commit", "-m", "Fixture", cwd=root)


@pytest.mark.asyncio
async def test_reimport_preserves_old_dirty_worktree_and_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    await repository(cache, monkeypatch)
    old = Task(id=uuid.uuid4(), external_key="TRELLO-example")
    old_path, new_path = tmp_path / "old", tmp_path / "new"
    old_branch = await add_task_worktree(cache, old_path, old, "main")
    old_revision = await run_git("rev-parse", "HEAD", cwd=old_path)
    (old_path / "source.py").write_text("important unfinished edit\n")
    fresh = Task(id=uuid.uuid4(), external_key=old.external_key)
    branch = await add_task_worktree(cache, new_path, fresh, "main")
    assert branch != old_branch and str(fresh.id) in branch
    assert (old_path / "source.py").read_text() == "important unfinished edit\n"
    assert await run_git("rev-parse", "HEAD", cwd=old_path) == old_revision
    assert (new_path / "source.py").read_text() == "value = 1\n"
    fresh.branch_name = branch
    assert task_branch(fresh) == branch


@pytest.mark.asyncio
async def test_unoccupied_existing_branch_is_never_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    await repository(cache, monkeypatch)
    await run_git("branch", "agent/trello-example", cwd=cache)
    old_revision = await run_git("rev-parse", "agent/trello-example", cwd=cache)
    fresh = Task(id=uuid.uuid4(), external_key="TRELLO-example")
    branch = await add_task_worktree(cache, tmp_path / "new", fresh, "main")
    assert branch != "agent/trello-example"
    assert await run_git("rev-parse", "agent/trello-example", cwd=cache) == old_revision


@pytest.mark.asyncio
async def test_full_file_limit_recovers_with_focused_range_and_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await repository(tmp_path, monkeypatch)
    (tmp_path / "source.py").write_text("# filler " + "x" * 200 + "\n" + "value = 1\n" * 20000)
    tools = RepositoryTools([(".", tmp_path)], 20, max_bytes=2000)
    full = json.loads(await tools.execute("read_repository_files", '{"paths":["source.py"]}'))
    assert full[0]["status"] == "CONTEXT_LIMIT"
    assert "read_repository_ranges" in full[0]["reason"]
    snippets = json.loads(
        await tools.execute("search_repository_snippets", '{"query":"value =","pattern":"*.py"}')
    )
    assert snippets[0]["line"] == 2
    focused = json.loads(
        await tools.execute(
            "read_repository_ranges",
            '{"ranges":[{"path":"source.py","start_line":2,"end_line":4}]}',
        )
    )
    assert focused[0]["content"] == "value = 1\n" * 3
    assert focused[0]["status"] == "LOADED_RANGE" and focused[0]["next_line"] == 5
    assert tools.remaining < 2000
    assert "value =" not in json.dumps(tools.last_trace)
    assert tools.last_trace["results"][0]["status"] == "LOADED_RANGE"


@pytest.mark.asyncio
async def test_range_batch_preserves_valid_results_and_rejects_secret_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await repository(tmp_path, monkeypatch)
    (tmp_path / ".env").write_text("TOP_SECRET=value")
    (tmp_path / "alias.py").symlink_to(tmp_path / ".env")
    tools = RepositoryTools([(".", tmp_path)], 10)
    result = json.loads(
        await tools.execute(
            "read_repository_ranges",
            json.dumps(
                {
                    "ranges": [
                        {"path": path, "start_line": 1, "end_line": 20}
                        for path in ["../outside", "alias.py", "source.py"]
                    ]
                }
            ),
        )
    )
    assert [item["status"] for item in result] == ["NOT_READABLE", "NOT_READABLE", "LOADED_RANGE"]
    assert "TOP_SECRET" not in json.dumps(result)


@pytest.mark.asyncio
async def test_native_thinker_omits_bulk_manifest_and_repository_rag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiler = ContextCompiler(AsyncMock(), native_repository_tools=True)
    monkeypatch.setattr(compiler, "_base", lambda *_: {"task": {"title": "Test"}})
    monkeypatch.setattr(compiler, "_include_conversation", AsyncMock())
    monkeypatch.setattr(compiler, "_persistent_memory", AsyncMock(return_value={}))
    monkeypatch.setattr(compiler, "_previous_checkpoint", AsyncMock(return_value=None))
    knowledge = AsyncMock(return_value=[])
    monkeypatch.setattr(compiler, "_knowledge", knowledge)
    monkeypatch.setattr(
        compiler, "_finish", AsyncMock(side_effect=lambda task, job, context, started: context)
    )
    monkeypatch.setattr(
        "app.infrastructure.workers.context_compiler.run_git",
        AsyncMock(return_value="\n".join(f"backend/app/file_{i}.py" for i in range(2000))),
    )
    scoped = SimpleNamespace(
        path=Path("/tmp/test"),
        repository=SimpleNamespace(
            id=uuid.uuid4(),
            owner="owner",
            name="repo",
            default_branch="main",
            latest_sha="a",
            indexed_sha="old",
        ),
    )
    context = await compiler.compile_for_scoped_thinker(
        SimpleNamespace(), SimpleNamespace(), [scoped]
    )
    assert context["repositories"][0]["directory_outline"] == "backend"
    assert "tracked_files" not in context["repositories"][0]
    assert context["repositories"][0]["retrieved_knowledge"] == []
    assert knowledge.await_count == 1  # Manual/global knowledge is still included.


def test_cache_key_stable_across_task_payload_changes() -> None:
    first = OpenAIProvider._payload(ProviderRequest(model="test", system="stable", prompt="task A"))
    second = OpenAIProvider._payload(
        ProviderRequest(model="test", system="stable", prompt="task B")
    )
    assert first["prompt_cache_key"] == second["prompt_cache_key"]


def test_stream_retains_cache_read_and_write_usage() -> None:
    event = normalize_stream_event(
        "openai",
        {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 200},
                }
            },
        },
    )
    assert event is not None
    assert event.cached_input_tokens == 800 and event.cache_write_tokens == 200
