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
    redact_credentials,
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
