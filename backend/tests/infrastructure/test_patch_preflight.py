from unittest.mock import AsyncMock

import pytest

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.infrastructure import patch_pipeline, patch_preflight
from app.agent_runtime.infrastructure.patch_evidence import compact_failure


@pytest.mark.parametrize(
    "checks,category,action",
    [
        ({"checks": [{"exit_code": -1, "runtime_error": True}]}, "ENVIRONMENT", "STOP_RUNTIME"),
        ({"error": "Patch rejected: stale source"}, "PATCH_APPLICATION", "BOUNDED_REPAIR"),
        ({"checks": [{"name": "typecheck", "exit_code": 1}]}, "CHECK_FAILURE", "BOUNDED_REPAIR"),
        ({"error": "Unknown tool protocol"}, "UNKNOWN", "STOP_RUNTIME"),
    ],
)
def test_failure_evidence_preserves_uncertainty(checks, category, action):
    assert compact_failure(checks)["failure"] == {"category": category, "action": action}


def test_preflight_checks_only_tools_needed_for_selected_files(tmp_path, monkeypatch):
    monkeypatch.setattr(patch_preflight.shutil, "which", lambda name: "/bin/" + name)
    assert patch_preflight.patch_preflight(tmp_path, ["settings.toml"])["ready"]
    result = patch_preflight.patch_preflight(tmp_path, ["frontend/src/Window.svelte"])
    assert result["missing_tools"] == [
        "frontend/node_modules/.bin/eslint",
        "frontend/node_modules/.bin/prettier",
    ]


@pytest.mark.asyncio
async def test_missing_runtime_stops_before_any_patch_request(tmp_path, monkeypatch):
    harness = patch_pipeline.PatchPipelineHarness(
        HarnessSettings(model="gpt-5.6-terra", workspace=tmp_path, instructions="original")
    )
    harness.root, harness.logs = tmp_path / "state", tmp_path / "logs"
    await harness.start()
    monkeypatch.setattr(harness, "_start_sandbox", lambda: None)
    monkeypatch.setattr(
        harness,
        "operation",
        AsyncMock(
            return_value={
                "sources": [{"path": "a.py", "sha256": "hash", "text": "pass"}],
                "preflight": {"ready": False, "missing_tools": ["python module ruff"]},
            }
        ),
    )
    monkeypatch.setattr(
        patch_pipeline, "workspace_facts", AsyncMock(return_value={"diff_fingerprint": "diff"})
    )
    receipt = await harness.run_turn("fix original")
    assert receipt.failure_code == "PATCH_TOOL_FAILURE"
    assert "python module ruff" in receipt.summary
    assert not any(entry["type"] == "patch_request" for entry in harness.history)
