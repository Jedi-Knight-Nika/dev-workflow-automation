import json
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.domain.usage import Pricing
from app.agent_runtime.infrastructure.bounded_inference import BoundedInference, BoundedStop
from app.agent_runtime.infrastructure.patch_contract import FORMAT
from app.agent_runtime.infrastructure.patch_pipeline import PatchPipelineHarness
from app.agent_runtime.infrastructure.patch_wire import request_payload
from app.teams.domain.profiles import AgentProfile, RoleKind


@pytest.mark.parametrize(
    "scenario", ["success", "invalid_artifact", "unknown_usage", "truncated", "budget"]
)
async def test_deepseek_bounded_purchase_receipt_and_fail_closed(tmp_path, monkeypatch, scenario):
    settings = HarnessSettings(
        "deepseek-flash",
        tmp_path,
        "contract",
        provider="deepseek",
        pricing=Pricing(Decimal(2), Decimal(10), Decimal("0.2")),
        max_cost_usd=Decimal("0.00001") if scenario == "budget" else Decimal(1),
    )
    h = PatchPipelineHarness(settings)
    h.root, h.logs = tmp_path / "state", tmp_path / "logs"
    await h.start()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-only")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = []

    def respond(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert payload["reasoning_effort"] == "low"  # medium ceiling never maps to high
        assert payload["response_format"] == {"type": "json_object"}
        assert "tools" not in payload and "max_output_tokens" not in payload
        artifact = {"outcome": "PATCH", "summary": "fix: example", "edits": []}
        if scenario == "invalid_artifact":
            artifact["shell"] = "not allowed"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if scenario == "truncated" else "stop",
                        "message": {"content": json.dumps(artifact)},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_cache_hit_tokens": None if scenario == "unknown_usage" else 10,
                },
            },
        )

    inference = BoundedInference(h)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        if scenario == "success":
            assert (
                await inference.generate(
                    client,
                    kind="patch",
                    instructions="contract",
                    packet={},
                    schema=FORMAT,
                    effort="medium",
                )
            )["outcome"] == "PATCH"
        else:
            with pytest.raises(ValueError):
                await inference.generate(
                    client,
                    kind="patch",
                    instructions="contract",
                    packet={},
                    schema=FORMAT,
                    effort="medium",
                )
        if scenario == "unknown_usage":
            with pytest.raises(BoundedStop, match="Unknown usage"):
                await inference.generate(
                    client, kind="patch", instructions="contract", packet={}, schema=FORMAT
                )
    assert len(calls) == (0 if scenario == "budget" else 1)
    if scenario in {"success", "invalid_artifact", "truncated"}:
        assert inference.totals["input_tokens"] == 100
        assert any(item["type"] == "bounded_usage" for item in h.history)


def test_deepseek_requires_explicit_patch_profile_and_never_raises_medium_to_high():
    assert AgentProfile(RoleKind.DEVELOPER, "Experiment", "deepseek", "deepseek-flash", "patch")
    for harness in ("codex", "responses", "claude"):
        with pytest.raises(ValueError):
            AgentProfile(RoleKind.DEVELOPER, "Experiment", "deepseek", "deepseek-flash", harness)
    assert request_payload("deepseek", "deepseek-flash", "contract", {}, FORMAT, "none", 100)[
        "thinking"
    ] == {"type": "disabled"}


@pytest.mark.parametrize(
    "failures,attempts,success",
    [
        ([{"lint", "types"}, {"types"}, set()], 3, True),
        ([{"lint"}, {"lint"}], 2, False),
        ([{"lint"}, {"lint", "types"}], 2, False),
    ],
)
async def test_actual_work_unit_extends_only_when_checks_improve(
    tmp_path, monkeypatch, failures, attempts, success
):
    from app.agent_runtime.infrastructure import adaptive_patch
    from app.agent_runtime.infrastructure.work_plan import ExecutionMode, WorkGraph, WorkUnit

    h = PatchPipelineHarness(HarnessSettings("fixture", tmp_path, "contract", effort="medium"))
    h.root, h.logs = tmp_path / "state", tmp_path / "logs"
    await h.start()
    execution = adaptive_patch.AdaptivePatchExecution(h, ExecutionMode.STRUCTURED_MULTI_PATCH)
    unit = WorkUnit(
        id="fix",
        objective="Fix errors",
        candidate_files=["app.py"],
        depends_on=[],
        acceptance_checks=[],
        exported_contracts=[],
    )
    graph = WorkGraph(objective="Fix errors", units=[unit], integration_invariants=[])
    count = 0

    async def operation(name, args):
        nonlocal count
        if name == "prepare":
            return {"sources": [{"path": "app.py", "sha256": "current", "text": "source"}]}
        if name == "apply":
            return {"changed_files": ["app.py"]}
        assert name == "check"
        failing = failures[count]
        count += 1
        return {
            "exit_code": int(bool(failing)),
            "checks": [
                {"name": name, "exit_code": int(name in failing)} for name in ("lint", "types")
            ],
        }

    monkeypatch.setattr(h, "operation", operation)
    monkeypatch.setattr(
        execution,
        "facts",
        AsyncMock(
            return_value={
                "workspace_head": "head",
                "diff_fingerprint": "diff",
                "changed_files": ["app.py"],
            }
        ),
    )
    generate = AsyncMock(
        return_value={
            "outcome": "PATCH",
            "summary": "fix",
            "edits": [{"path": "app.py", "old_text": "source", "new_text": "fixed"}],
        }
    )
    monkeypatch.setattr(execution.inference, "generate", generate)
    async with httpx.AsyncClient() as client:
        if success:
            assert (await execution.unit(client, "Fix errors", graph, unit))["status"] == "READY"
        else:
            with pytest.raises(BoundedStop):
                await execution.unit(client, "Fix errors", graph, unit)
    assert generate.await_count == attempts
    if success:
        assert generate.await_args_list[-1].kwargs["effort"] == "medium"
