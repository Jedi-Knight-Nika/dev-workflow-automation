import json
from dataclasses import asdict
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.domain.model_policy import ModelPolicy, PricedModel
from app.agent_runtime.domain.usage import Pricing, Usage
from app.agent_runtime.infrastructure.adaptive_patch import AdaptivePatchExecution
from app.agent_runtime.infrastructure.bounded_inference import BoundedInference, BoundedStop
from app.agent_runtime.infrastructure.models import PricingCatalog
from app.agent_runtime.infrastructure.patch_contract import FORMAT
from app.agent_runtime.infrastructure.patch_pipeline import PatchPipelineHarness
from app.agent_runtime.infrastructure.routed_usage import settled_cost
from app.agent_runtime.infrastructure.work_plan import ExecutionMode, WorkGraph, WorkUnit


@pytest.mark.parametrize("invalid", ["missing", "malformed", "stale", "wrong_turn"])
def test_invalid_typed_artifacts_retain_valid_provider_billing(invalid):
    from uuid import uuid4

    from app.agent_runtime.domain.handoffs import result_packet, work_packet
    from app.agent_runtime.infrastructure.agent_codec import canonical
    from app.agent_runtime.infrastructure.typed_receipt import decode_receipt

    work = work_packet(uuid4(), 2, "head", "Exact requirement")
    result = canonical(
        result_packet(
            work,
            status="completed",
            summary="IMPLEMENTED",
            turn_id="turn",
            failure_code=None,
            checks=[],
        )
    )
    if invalid == "malformed":
        result["version"] = 999
    if invalid == "stale":
        result["requirement_revision"] = 1
    if invalid == "wrong_turn":
        result["payload"]["turn_id"] = "other"
    payload = {
        "native_session_id": "session",
        "native_turn_id": "turn",
        "summary": "IMPLEMENTED",
        "status": "completed",
        "usage": asdict(Usage(100, 20, 10, 0)),
        "result": None if invalid == "missing" else result,
    }
    receipt = decode_receipt(payload, work)
    assert receipt.status == "failed" and receipt.failure_code == "INVALID_AGENT_RESULT"
    assert receipt.usage == Usage(100, 20, 10, 0) and receipt.native_turn_id == "turn"


async def test_routed_purchases_share_budget_and_retain_each_model_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only")
    price = Pricing(Decimal(1), Decimal(2), Decimal(0))
    expensive = Pricing(Decimal(1000), Decimal(2000), Decimal(0))
    route = PricedModel(
        ModelPolicy("openai", "chosen-planner", "planning"), expensive, "price-route"
    )
    h = PatchPipelineHarness(
        HarnessSettings(
            "base",
            tmp_path,
            "contract",
            pricing=price,
            pricing_id="price-base",
            routed_models=(route,),
            max_cost_usd=Decimal(25),
            effort="low",
        )
    )
    h.root, h.logs = tmp_path / "state", tmp_path / "logs"
    await h.start()
    payloads = []

    def respond(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "input_tokens_details": {"cached_tokens": 10},
                },
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {"outcome": "PATCH", "summary": "fix", "edits": []}
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    inference = BoundedInference(h)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for kind in ("patch", "planning"):
            await inference.generate(
                client,
                kind=kind,
                instructions="contract",
                packet={},
                schema=FORMAT,
                output_limit=100,
            )
        assert [p["model"] for p in payloads] == ["base", "chosen-planner"]
        assert inference.cost_usd == Decimal("0.13013")
        assert [r["pricing_id"] for r in inference.priced_requests] == ["price-base", "price-route"]
        h.settings = HarnessSettings(
            "base", tmp_path, "contract", pricing=price, max_cost_usd=Decimal("0.13")
        )
        with pytest.raises(BoundedStop, match="cost headroom"):
            await inference.generate(
                client, kind="patch", instructions="contract", packet={}, schema=FORMAT
            )
        assert len(payloads) == 2


@pytest.mark.parametrize("tamper", [None, "model", "tokens", "price"])
def test_controller_recomputes_routed_cost_with_admitted_prices(tamper):
    usage = Usage(100, 20, 10, 0)
    price = PricingCatalog(
        provider="openai",
        model="chosen",
        input_per_million=Decimal(2),
        output_per_million=Decimal(10),
        cached_input_per_million=Decimal(0),
    )
    request = {
        "pricing_id": "admitted",
        "provider": "openai",
        "model": "chosen",
        "usage": asdict(usage),
    }
    if tamper == "model":
        request["model"] = "different"
    if tamper == "price":
        request["pricing_id"] = "unadmitted"
    if tamper == "tokens":
        request["usage"]["input_tokens"] = 200
    assert settled_cost([request], usage, {"admitted": price}) == (
        None if tamper else Decimal("0.00038")
    )


@pytest.mark.parametrize("failure", ["PATCH_STALLED", "PATCH_REGRESSING", "USAGE_INCOMPLETE"])
async def test_replan_changes_strategy_once_without_resetting_shared_usage(
    tmp_path, monkeypatch, failure
):
    h = PatchPipelineHarness(HarnessSettings("fixture", tmp_path, "contract"))
    h.root, h.logs = tmp_path / "state", tmp_path / "logs"
    await h.start()
    execution = AdaptivePatchExecution(h, ExecutionMode.STRUCTURED_MULTI_PATCH)
    unit = WorkUnit(
        id="fix",
        objective="Fix",
        candidate_files=["app.py"],
        depends_on=[],
        acceptance_checks=[],
        exported_contracts=[],
    )
    graph = WorkGraph(objective="Original", units=[unit], integration_invariants=[])
    survey = {"repository_paths": ["app.py"]}
    monkeypatch.setattr(execution, "plan", AsyncMock(return_value=graph))
    monkeypatch.setattr(
        execution, "unit", AsyncMock(side_effect=BoundedStop(failure, "Exact failure"))
    )
    monkeypatch.setattr(
        execution, "investigate", AsyncMock(return_value={"root_cause": "new evidence"})
    )
    monkeypatch.setattr(execution, "facts", AsyncMock(return_value={"workspace_head": "head"}))
    monkeypatch.setattr(h, "operation", AsyncMock(return_value=survey))
    execution.inference.calls = {"patch": 5}
    execution.inference.cost_usd = Decimal("0.2")
    async with httpx.AsyncClient() as client:
        with pytest.raises(BoundedStop):
            await execution.execute_graph(client, "Exact original requirement", survey, None, {})
    assert execution.replans == (1 if failure == "PATCH_STALLED" else 0)
    assert execution.unit.await_count == (2 if failure == "PATCH_STALLED" else 1)
    assert execution.inference.calls == {"patch": 5} and execution.inference.cost_usd == Decimal(
        "0.2"
    )
    if failure == "PATCH_STALLED":
        evidence = execution.investigate.call_args.args[2]["replan_evidence"]
        assert evidence["reason"] == "Exact failure"
