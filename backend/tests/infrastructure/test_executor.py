from pathlib import Path

import pytest
from pydantic import ValidationError

from app.infrastructure.workers.executor import (
    ExecutorProposal,
    FileWrite,
    ReviewerProposal,
    apply_proposal,
    credential_subprocess_environment,
    dependency_setup_commands,
    detected_checks,
    merge_requested_file_context,
    redact_credentials,
    requested_file_context,
)


def test_executor_applies_only_workspace_relative_files(tmp_path: Path) -> None:
    proposal = ExecutorProposal(
        summary="updated",
        files=[FileWrite(path="src/example.py", content="value = 1\n")],
    )

    apply_proposal(tmp_path, proposal)

    assert (tmp_path / "src/example.py").read_text() == "value = 1\n"


def test_executor_rejects_path_escape(tmp_path: Path) -> None:
    proposal = ExecutorProposal(
        summary="unsafe",
        files=[FileWrite(path="../outside.txt", content="no")],
    )

    with pytest.raises(ValueError, match="Unsafe workspace path"):
        apply_proposal(tmp_path, proposal)


@pytest.mark.asyncio
async def test_executor_loads_explicit_tracked_context_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "app" / "teams.py"
    source.parent.mkdir(parents=True)
    source.write_text("TEAM_SETTING = True\n")

    async def tracked_file(*args: str, cwd: Path | None = None, **_: object) -> str:
        assert args == ("ls-files",)
        assert cwd == tmp_path
        return "app/teams.py"

    monkeypatch.setattr("app.infrastructure.workers.executor.run_git", tracked_file)

    result = await requested_file_context([(".", tmp_path)], ["app/teams.py", "../secret"])

    assert result[0] == {
        "path": "app/teams.py",
        "requested_path": "app/teams.py",
        "status": "LOADED",
        "content": "TEAM_SETTING = True\n",
    }
    assert result[1] == {"path": "../secret", "status": "INVALID_PATH"}


@pytest.mark.asyncio
async def test_executor_resolves_a_unique_requested_basename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "app" / "db" / "models" / "teams.py"
    source.parent.mkdir(parents=True)
    source.write_text("TEAM_SETTING = True\n")

    async def tracked_files(*args: str, **_: object) -> str:
        assert args == ("ls-files",)
        return "app/db/models/teams.py"

    monkeypatch.setattr("app.infrastructure.workers.executor.run_git", tracked_files)

    result = await requested_file_context([(".", tmp_path)], ["teams.py"])

    assert result[0]["status"] == "LOADED"
    assert result[0]["path"] == "app/db/models/teams.py"
    assert result[0]["requested_path"] == "teams.py"


def test_executor_accumulates_loaded_context_between_rounds() -> None:
    first = [{"path": "a.py", "requested_path": "a.py", "status": "LOADED", "content": "a"}]
    second = [
        {"path": "a.py", "requested_path": "a.py", "status": "LOADED", "content": "a"},
        {"path": "b.py", "requested_path": "b.py", "status": "LOADED", "content": "b"},
    ]

    assert [item["path"] for item in merge_requested_file_context(first, second)] == [
        "a.py",
        "b.py",
    ]


@pytest.mark.asyncio
async def test_duplicate_source_requests_do_not_consume_remaining_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.py").write_text("a" * 50)
    (tmp_path / "b.py").write_text("b" * 10)

    async def tracked(*args: str, **kwargs: object) -> str:
        return "a.py\nb.py"

    monkeypatch.setattr("app.infrastructure.workers.executor.run_git", tracked)
    existing = [{"path": "a.py", "status": "LOADED", "content": "a" * 50}]
    result = await requested_file_context(
        [(".", tmp_path)], ["a.py", "b.py"], max_context_bytes=10, existing_context=existing
    )
    assert [item["status"] for item in result] == ["LOADED", "LOADED"]
    merged = merge_requested_file_context(existing, result)
    assert sum(len(item["content"]) for item in merged) == 60


def test_resolved_context_request_removes_obsolete_failure() -> None:
    result = merge_requested_file_context(
        [{"path": "a.py", "status": "CONTEXT_LIMIT"}],
        [{"path": "a.py", "status": "LOADED", "content": "a"}],
    )
    assert len(result) == 1
    assert result[0]["status"] == "LOADED"


def test_checks_are_derived_from_manifests_not_model_commands(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"check":"svelte-check","deploy":"dangerous"}}'
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='sample'\n")

    assert detected_checks(tmp_path) == [
        ["npm", "run", "check"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pytest", "-q"],
    ]


def test_dependency_setup_uses_only_committed_lockfiles(tmp_path: Path) -> None:
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / "uv.lock").write_text("")

    assert dependency_setup_commands(tmp_path) == [
        ["npm", "ci"],
        ["uv", "sync", "--frozen", "--all-extras"],
    ]


def test_registry_environment_is_whitelisted_and_output_is_redacted() -> None:
    supplied = {
        "NODE_AUTH_TOKEN": "npm-secret",
        "UV_INDEX_PASSWORD": "pypi-secret",
        "DANGEROUS_OVERRIDE": "ignored",
    }

    assert credential_subprocess_environment(supplied) == {
        "NODE_AUTH_TOKEN": "npm-secret",
        "UV_INDEX_PASSWORD": "pypi-secret",
    }
    assert redact_credentials("npm-secret pypi-secret", supplied) == "[REDACTED] [REDACTED]"


def test_reviewer_result_requires_structured_findings() -> None:
    review = ReviewerProposal.model_validate(
        {
            "result": "FAIL_ACTIONABLE",
            "summary": "Regression found",
            "findings": [
                {"severity": "HIGH", "path": "src/service.py", "line": 42, "message": "Null crash"}
            ],
        }
    )

    assert review.result == "FAIL_ACTIONABLE"
    assert review.findings[0].line == 42

    with pytest.raises(ValidationError):
        ReviewerProposal.model_validate({"result": "MAYBE", "summary": "unclear"})
