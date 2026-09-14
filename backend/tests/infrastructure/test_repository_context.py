import json

from app.agent_runtime.infrastructure.prompt_cache import bounded_request_context
from app.agent_runtime.infrastructure.repository_context import (
    MAX_CONTEXT_BYTES,
    repository_context,
)


def test_project_facts_reuse_across_worktrees_and_refresh(tmp_path):
    contexts = []
    for task in ("one", "two"):
        workspace = tmp_path / task
        workspace.mkdir()
        (workspace / "frontend").mkdir()
        (workspace / "frontend/package.json").write_text(
            json.dumps(
                {
                    "name": "frontend",
                    "scripts": {"check": "svelte-check", "format": "prettier --write ."},
                }
            )
        )
        (workspace / "README.md").write_text("Project architecture and conventions")
        (workspace / "frontend/source.ts").write_text(task)
        contexts.append(repository_context(workspace))
    assert contexts[0] == contexts[1]  # Task path and current implementation are not shared memory.
    (tmp_path / "two/README.md").write_text("Updated conventions")
    assert repository_context(tmp_path / "two") != contexts[0]
    assert "svelte-check" in contexts[0]["text"]


def test_optional_repository_evidence_is_bounded_and_does_not_follow_symlinks(tmp_path):
    workspace = tmp_path / "repository"
    workspace.mkdir()
    secret = tmp_path / "private"
    secret.write_text("NEVER INCLUDE THIS")
    (workspace / "AGENTS.md").symlink_to(secret)
    (workspace / ".env").write_text("NEVER INCLUDE THIS")
    (workspace / "README.md").write_text("界" * 12000)
    context = repository_context(workspace)
    assert "NEVER INCLUDE THIS" not in context["text"]
    assert len(context["text"].encode()) <= MAX_CONTEXT_BYTES


def test_stable_prefix_precedes_different_tasks_without_context_duplication():
    shared = {"text": "Project conventions", "fingerprint": "not trusted"}
    packets = [
        {
            "original_requirement_and_guidance": task,
            "repository_context": shared,
            "repository_evidence": {"repository_context": shared, "sha": task},
        }
        for task in ("Task one", "Task two")
    ]
    first, second = [bounded_request_context("gpt-5.6-terra", "contract", p) for p in packets]
    assert first["prompt_cache_key"] == second["prompt_cache_key"]
    assert first["input"][0] == second["input"][0]
    assert first["input"][1] != second["input"][1]
    assert first["input"][0]["role"] == "user"  # Repository text is not system policy.
    assert first["input"][0]["content"][0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert first["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    assert "repository_context" not in first["input"][1]["content"]
    assert packets[0]["repository_context"] == shared  # Never mutate audit packets.
    changed = bounded_request_context(
        "gpt-5.6-terra", "contract", {"repository_context": {"text": "New conventions"}}
    )
    assert changed["prompt_cache_key"] != first["prompt_cache_key"]
