"""Focused regression checks for call bounds, fresh units and fail-closed recovery."""

import json
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.domain.usage import Pricing
from app.agent_runtime.infrastructure import adaptive_patch, patch_pipeline
from app.agent_runtime.infrastructure.adaptive_patch import execution_mode
from app.agent_runtime.infrastructure.patch_context import compile_source
from app.agent_runtime.infrastructure.patch_evidence import integration_repair_paths
from app.agent_runtime.infrastructure.patch_tools import apply
from app.agent_runtime.infrastructure.work_plan import ExecutionMode, WorkGraph


def plan():
    return {
        "objective": "Update both surfaces",
        "integration_invariants": ["Keep the existing API"],
        "units": [
            {
                "id": name,
                "objective": "Update " + name,
                "candidate_files": [name + ".py"],
                "depends_on": ["first"] if name == "second" else [],
                "acceptance_checks": ["Existing behavior preserved"],
                "exported_contracts": [],
            }
            for name in ["first", "second"]
        ],
    }


def test_plan_rejects_cycles_and_keeps_fast_default():
    assert execution_mode("ordinary task") == ExecutionMode.FAST_PATCH
    graph = WorkGraph.model_validate(plan())
    assert [u.id for u in graph.ordered_units()] == ["first", "second"]
    invalid = plan()
    invalid["units"][0]["depends_on"] = ["second"]
    with pytest.raises(ValidationError):
        WorkGraph.model_validate(invalid)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("metadata.py:12: error", ["metadata.py"]),
        ("./data.py:12: error", ["data.py"]),
        ("frontend/src/Panel.svelte:12: error", ["frontend/src/Panel.svelte"]),
        ("src/Panel.svelte(12, 3): error", ["frontend/src/Panel.svelte"]),
        ("data.pyi:12: error", []),
        ("other/src/Panel.svelte:12: error", []),
    ],
)
def test_integration_repair_matches_complete_file_paths(error, expected):
    paths = ["data.py", "metadata.py", "frontend/src/Panel.svelte", "unrelated.py"]
    checks = {"checks": [{"name": "lint", "exit_code": 1, "stdout_tail": error}]}
    assert integration_repair_paths(checks, paths) == expected


def test_integration_repair_ignores_success_output_and_keeps_bounded_fallback():
    checks = {"checks": [{"name": "lint", "exit_code": 0, "stdout_tail": "data.py"}]}
    paths = ["data.py", "metadata.py"]
    assert integration_repair_paths(checks, paths) == paths


def test_large_source_is_bounded_hashed_and_refreshes(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("# irrelevant\n" * 4000 + "def important_action():\n    return 1\n")
    source = compile_source(tmp_path, "example.py", "important action", 6000)
    assert source["complete"] is False
    assert any("def important_action" in r["text"] for r in source["ranges"])
    assert sum(len(r["text"].encode()) for r in source["ranges"]) <= 6000
    target.write_text(target.read_text().replace("return 1", "return 2"))
    assert (
        compile_source(tmp_path, "example.py", "important action", 6000)["sha256"]
        != source["sha256"]
    )


def test_prepare_keeps_unit_objective_outside_supervisor_annotations(tmp_path, monkeypatch):
    from app.agent_runtime.infrastructure import patch_tools

    (tmp_path / "example.py").write_text("value = 1\n")
    queries = []

    def investigate(workspace, objective, **kwargs):
        queries.append(objective)
        return {"candidate_paths": ["example.py"], "repo_map": [], "sha": "base"}

    monkeypatch.setattr(patch_tools, "investigate", investigate)
    patch_tools.prepare(
        tmp_path,
        'Original task\nAdvisory Supervisor annotations\n{"interpretation": "advice"}',
        paths=["example.py"],
        work_objective="Update the query filter",
    )
    assert queries == ["Update the query filter\nOriginal task\n"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"paths": []},
        {"paths": ["example.py", "example.py"]},
        {"paths": ["example.py"], "new_files": ["outside.py"]},
        {"paths": ["example.py"], "new_files": ["example.py", "example.py"]},
    ],
)
def test_invalid_source_selection_does_not_scan_repository(tmp_path, monkeypatch, arguments):
    from unittest.mock import Mock

    from app.agent_runtime.infrastructure import patch_tools

    scan = Mock()
    monkeypatch.setattr(patch_tools, "investigate", scan)
    with pytest.raises(ValueError):
        patch_tools.prepare(tmp_path, "Original task", **arguments)
    scan.assert_not_called()


def test_new_file_requires_absence_and_source_scope(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    patch = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+value = 1\n"
    assert apply(tmp_path, patch, {"new.py": "MISSING"}) == ["new.py"]
    assert (tmp_path / "new.py").read_text() == "value = 1\n"
    with pytest.raises(ValueError):
        apply(tmp_path, patch, {"new.py": "MISSING"})
    with pytest.raises(ValueError):
        apply(tmp_path, patch.replace("new.py", "../outside.py"), {"../outside.py": "MISSING"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "repair",
        "infra",
        "unknown_usage",
        "invalid_plan",
        "investigate",
        "investigate_search",
        "budget",
    ],
)
async def test_bounded_execution(tmp_path, monkeypatch, scenario):
    settings = HarnessSettings(
        model="gpt-5.6-terra",
        workspace=tmp_path,
        instructions="original",
        effort="low",
        max_cost_usd=Decimal("0.001") if scenario == "budget" else Decimal(5),
        pricing=Pricing(Decimal(2), Decimal(12), Decimal("0.2"), Decimal("2.5")),
    )
    h = patch_pipeline.PatchPipelineHarness(settings)
    h.root, h.logs = tmp_path / "state", tmp_path / "logs"
    await h.start()
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(h, "_start_sandbox", lambda: None)
    facts = {"workspace_head": "head", "diff_fingerprint": "baseline", "changed_files": []}
    monkeypatch.setattr(
        adaptive_patch, "workspace_facts", AsyncMock(side_effect=lambda *a: dict(facts))
    )
    calls, operations = [], []

    async def operation(name, args):
        operations.append((name, args))
        if name == "survey":
            return {"repository_paths": ["first.py", "second.py"], "repo_map": [], "sha": "head"}
        if name in {"prepare", "inspect"}:
            return {
                "sources": [
                    {"path": p, "sha256": facts["diff_fingerprint"], "text": "current source"}
                    for p in args["paths"]
                ]
            }
        if name == "apply":
            paths = list(args["hashes"])
            facts["changed_files"] = sorted(set(facts["changed_files"]) | set(paths))
            facts["diff_fingerprint"] = "changed-" + str(len(operations))
            return {"changed_files": paths}
        assert name == "check"
        failed = scenario == "infra" or (
            scenario == "repair" and sum(name == "check" for name, _ in operations) == 1
        )
        return {
            "exit_code": int(failed),
            "checks": [
                {
                    "name": "lint",
                    "exit_code": int(failed),
                    "runtime_error": scenario == "infra",
                }
            ],
            "paths": args["paths"],
        }

    monkeypatch.setattr(h, "operation", operation)

    def handle(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert "tools" not in payload and len(payload["input"]) == 1
        packet = json.loads(payload["input"][0]["content"])
        assert packet["original_requirement_and_guidance"].startswith("ORIGINAL task")
        kind = payload["text"]["format"]["name"]
        result = (
            {"graph": plan(), "blocked_reason": ""}
            if kind == "work_graph"
            else {"outcome": "PATCH", "summary": "fix: update surfaces", "patch": "patch"}
        )
        if kind == "investigation":
            result = {
                "root_cause": "Located surfaces",
                "relevant_files": ["first.py"],
                "evidence": ["Provided map"],
                "uncertainty": [],
                "inspect_paths": [],
                "ready": True,
            }
            if scenario == "investigate_search" and len(calls) == 1:
                result.update(
                    {"ready": False, "search_query": "surface", "inspect_paths": ["first.py"]}
                )
        if scenario == "invalid_plan":
            result["graph"]["units"][0]["candidate_files"] = ["outside.py"]
        if scenario == "repair" and packet.get("previous_failure"):
            result["patch"] = ""
        if "work_unit" in packet and packet["work_unit"]["id"] == "second":
            assert packet["completed_units"][0]["unit_id"] == "first"
            assert packet["completed_units"][0]["changed_files"] == ["first.py"]
            assert packet["sources"][0]["sha256"].startswith("changed-")
            assert "patch_response" not in json.dumps(packet)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(result)}],
                    }
                ],
                "usage": {}
                if scenario == "unknown_usage"
                else {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "input_tokens_details": {"cached_tokens": 0},
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(adaptive_patch.httpx, "AsyncClient", lambda **kw: client)
    mode = "BOUNDED_AGENTIC" if scenario.startswith("investigate") else "STRUCTURED_MULTI_PATCH"
    prompt = "ORIGINAL task\nAdvisory Supervisor annotations\n" + json.dumps(
        {"execution_mode": mode}
    )
    receipt = await h.run_turn(prompt)
    expected = {
        "success": 3,
        "repair": 4,
        "infra": 2,
        "unknown_usage": 1,
        "invalid_plan": 1,
        "investigate": 4,
        "investigate_search": 5,
        "budget": 0,
    }[scenario]
    assert len(calls) == expected
    assert receipt.status == (
        "completed"
        if scenario in {"success", "repair", "investigate", "investigate_search"}
        else "failed"
    )
    if scenario == "unknown_usage":
        assert receipt.usage.input_tokens is None
    else:
        assert receipt.usage.input_tokens == expected * 1000
    if receipt.status == "completed":
        assert operations[-1] == (
            "check",
            {"paths": ["first.py", "second.py"], "intermediate": False},
        )
        assert receipt.token_efficiency["completed_work_units"] == 2
        again = await h.run_turn(prompt)
        assert again.failure_code == "PATCH_ALREADY_ATTEMPTED"
        assert len(calls) == expected
        restored = patch_pipeline.PatchPipelineHarness(settings)
        restored.root = h.root
        await restored.resume(h.id)
        assert (await restored.run_turn(prompt)).failure_code == "PATCH_ALREADY_ATTEMPTED"
