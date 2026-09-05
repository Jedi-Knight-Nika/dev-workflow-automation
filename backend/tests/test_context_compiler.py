import json

import pytest

from app.infrastructure.workers.context_compiler import (
    MIN_CONTEXT_CHARS,
    ContextCompiler,
    fit_context,
)


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


def test_context_compiler_exposes_role_specific_entrypoints() -> None:
    for role in ("intake", "thinker", "executor", "reviewer"):
        assert hasattr(ContextCompiler, f"compile_for_{role}")
