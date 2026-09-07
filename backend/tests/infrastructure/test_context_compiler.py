import json

import pytest

from app.infrastructure.workers.context_compiler import (
    MIN_CONTEXT_CHARS,
    ContextCompiler,
    _repository_relevance_hint,
    _trim_complete_file_context,
    fit_context,
)
from app.infrastructure.workers.executor import _relevance_score, _relevance_terms


def test_context_is_trimmed_without_breaking_structured_json() -> None:
    context = {
        "task": {"description": "d" * 30_000},
        "job": {"payload": {"large": "p" * 10_000}},
        "repository": {"diff": "x" * 30_000},
        "retrieved_knowledge": [{"content": "k" * 5_000} for _ in range(5)],
        "open_findings": [{"message": "f" * 2_000} for _ in range(3)],
    }

    fitted = fit_context(context, MIN_CONTEXT_CHARS)

    assert len(json.dumps(fitted)) <= MIN_CONTEXT_CHARS
    assert fitted["repository"]["diff"].endswith("[TRUNCATED]")
    assert len(fitted["retrieved_knowledge"]) < 5


def test_essential_context_overflow_is_rejected() -> None:
    with pytest.raises(ValueError, match="Essential worker context"):
        fit_context({"essential": "x" * (MIN_CONTEXT_CHARS + 1)}, MIN_CONTEXT_CHARS)


def test_nested_repository_knowledge_and_old_conversation_are_trimmed() -> None:
    context = {
        "task": {"description": "small"},
        "repositories": [
            {
                "files": "x" * 12_000,
                "retrieved_knowledge": [{"content": "k" * 4_000} for _ in range(5)],
            }
        ],
        "internal_task_conversation": [
            {"body": "old" * 2_000},
            {"body": "latest instruction"},
        ],
    }

    fitted = fit_context(context, MIN_CONTEXT_CHARS)

    assert len(json.dumps(fitted, ensure_ascii=False)) <= MIN_CONTEXT_CHARS
    assert fitted["internal_task_conversation"][-1]["body"] == "latest instruction"
    assert len(fitted["repositories"][0]["retrieved_knowledge"]) < 5


def test_repository_context_trimming_keeps_only_complete_files() -> None:
    bundle = (
        "\n--- FILE: first.py ---\nfirst = True\n"
        "\n--- FILE: oversized.py ---\n" + "x" * 200 + "\n--- FILE: last.py ---\nlast = True\n"
        "\n--- TRACKED FILE MANIFEST ---\nfirst.py\noversized.py\nlast.py"
    )

    trimmed = _trim_complete_file_context(bundle, 100)

    assert "first = True" in trimmed
    assert "last = True" in trimmed
    assert "oversized.py" not in trimmed
    assert not trimmed.endswith("[TRUNCATED]")


def test_non_ascii_context_is_measured_without_escape_inflation() -> None:
    context = {"essential": "ა" * (MIN_CONTEXT_CHARS // 2)}

    assert fit_context(context, MIN_CONTEXT_CHARS) == context


def test_context_compiler_exposes_role_specific_entrypoints() -> None:
    for role in ("intake", "thinker", "executor", "reviewer"):
        assert hasattr(ContextCompiler, f"compile_for_{role}")


def test_repository_context_relevance_prioritizes_matching_paths_and_content() -> None:
    terms = _relevance_terms("make the frontend header and sidebar translucent")

    shell_score = _relevance_score(
        "frontend/src/routes/+layout.svelte", "<header><aside class='sidebar'>", terms
    )
    backend_score = _relevance_score("backend/app/main.py", "create application", terms)

    assert shell_score > backend_score


def test_repository_relevance_uses_goal_and_targets_not_full_plan_noise() -> None:
    hint = _repository_relevance_hint(
        {
            "task": {"title": "visual change", "description": ""},
            "technical_plan": {
                "summary": "shell styling",
                "data": {
                    "goal": "make header translucent",
                    "targets": ["frontend sidebar"],
                    "ordered_steps": ["unrelated noisy implementation detail"],
                },
            },
        }
    )

    assert "frontend sidebar" in hint
    assert "unrelated noisy" not in hint
