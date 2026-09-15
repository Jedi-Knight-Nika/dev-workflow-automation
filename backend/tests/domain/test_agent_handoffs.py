from dataclasses import replace
from uuid import uuid4

import pytest

from app.agent_runtime.domain.handoffs import (
    WorkOutcome,
    result_packet,
    validate_result,
    work_packet,
)
from app.agent_runtime.domain.model_policy import ModelPolicy
from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.infrastructure.runner import Manifest
from app.agent_runtime.infrastructure.structural_compression import compress, decompress


def result(work, summary="IMPLEMENTED\nfix: example"):
    return result_packet(
        work, status="completed", summary=summary, turn_id="turn-1", failure_code=None, checks=[]
    )


@pytest.mark.parametrize(
    "change", [{"task_id": uuid4()}, {"requirement_revision": 3}, {"current_sha": "old"}]
)
def test_result_cannot_cross_task_revision_or_sha(change):
    work = work_packet(uuid4(), 2, "head", "Keep exact human requirement")
    with pytest.raises(ValueError, match="different task"):
        validate_result(replace(result(work), **change), work)


def test_manifest_uses_one_canonical_request_and_rejects_conflicting_prose():
    work = work_packet(
        uuid4(), 1, None, "Exact requirement", invariants=("Keep existing behavior",)
    )
    manifest = Manifest(harness="patch", model="fixture", max_cost_usd=1, work_request=work)
    wire = manifest.model_dump(mode="json", exclude={"prompt"})
    assert Manifest.model_validate(wire).prompt == "Exact requirement"
    with pytest.raises(ValueError, match="differs"):
        Manifest.model_validate({**wire, "prompt": "A different task"})
    assert validate_result(result(work), work) == WorkOutcome.IMPLEMENTED
    assert validate_result(result(work, "Looks good"), work) == WorkOutcome.NEEDS_HUMAN


def test_dictionary_compression_preserves_values_and_literal_symbol_keys():
    original = {
        "~0": "literal",
        "errors": [{"compiler_error": "a != b\n|ს"}, {"compiler_error": "~0"}],
    }
    encoded = compress(original)
    assert "compiler_error" in encoded["dictionary"]
    assert encoded["packet"]["errors"][0]["~0"] == "a != b\n|ს"
    assert decompress(encoded) == original


@pytest.mark.parametrize(
    "packet", [{"~1": 1}, {"~00": 1}, {"~0": 1, "compiler_error": 2}, {"~x": 1}]
)
def test_dictionary_rejects_ambiguous_or_unknown_references(packet):
    with pytest.raises(ValueError):
        decompress({"dictionary": ["compiler_error"], "packet": packet})


def test_policy_routes_roundtrip_and_enforce_explicit_experiment_and_ceilings():
    route = {
        "provider": "openai",
        "model": "chosen-model",
        "role": "planning",
        "default_effort": "low",
    }
    policy = TokenEfficiencyPolicy.parse({"model_routes": [route], "adaptive_replans": 0})
    assert policy.model_routes[0].model == "chosen-model"
    for values in (
        {"model_routes": [route, route]},
        {"adaptive_replans": 2},
        {"model_routes": [{**route, "provider": "deepseek"}]},
        {"model_routes": [{**route, "allowed_modes": ["FAST_PATCH"]}]},
    ):
        with pytest.raises(ValueError):
            TokenEfficiencyPolicy.parse(values)
    with pytest.raises(ValueError):
        ModelPolicy("openai", "chosen", "planning", default_effort="high", max_effort="low")


def test_continuation_preserves_long_original_requirement_and_rejects_overflow():
    from app.agent_runtime.domain.session_changes import continuation_request

    original = "x" * 15000 + " REQUIRED FINAL CONSTRAINT"
    result = continuation_request(original, {"semantic_note": "Continue work"})
    assert result.startswith(original)
    with pytest.raises(ValueError, match="Complete requirement"):
        continuation_request("x" * 23990, {"semantic_note": "Continue work"})
