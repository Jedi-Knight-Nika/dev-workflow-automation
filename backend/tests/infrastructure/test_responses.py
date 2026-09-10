import hashlib
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.domain.usage import Pricing
from app.agent_runtime.infrastructure import responses
from app.agent_runtime.infrastructure.responses_tools import execute_tool, inspect_ranges
from app.agent_runtime.infrastructure.source_paths import source_path


def test_range_inspection_reuses_file_only_within_one_call(tmp_path, monkeypatch):
    path = tmp_path / "Window.svelte"
    path.write_text("first\nsecond\nthird\n")
    read_bytes = Path.read_bytes
    reads = []

    def read(source):
        reads.append(source)
        return read_bytes(source)

    monkeypatch.setattr(Path, "read_bytes", read)
    ranges = [{"path": path.name, "start": i, "end": i} for i in (1, 3)]
    result = inspect_ranges(tmp_path, ranges)
    assert reads == [path]
    assert [row["text"] for row in result] == ["first", "third"]
    assert result[0]["sha256"] == result[1]["sha256"]
    path.write_text("updated\nsecond\nthird\n")
    refreshed = inspect_ranges(tmp_path, ranges)
    assert reads == [path, path]
    assert refreshed[0]["text"] == "updated"
    assert refreshed[0]["sha256"] != result[0]["sha256"]
    with pytest.raises(ValueError, match="1-based"):
        inspect_ranges(tmp_path, [*ranges, {"path": path.name, "start": 0, "end": 1}])
    assert reads == [path, path]


@pytest.mark.asyncio
async def test_exact_edit_refuses_stale_source_and_escape(tmp_path):
    path = tmp_path / "Window.svelte"
    path.write_text("<p>old</p>")
    args = {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "old_text": "old",
        "new_text": "new",
    }
    await execute_tool(tmp_path, "edit_file", args)
    assert path.read_text() == "<p>new</p>"
    with pytest.raises(ValueError, match="changed"):
        await execute_tool(tmp_path, "edit_file", args)
    (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
    for name in ("../outside", "/etc/passwd", "alias/Window.svelte", ".git/config"):
        with pytest.raises(ValueError):
            source_path(tmp_path, name)


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect", [False, True])
async def test_compound_check_has_no_wait_turn_and_uncertain_usage_is_not_zero(
    tmp_path, monkeypatch, disconnect
):
    settings = HarnessSettings(
        model="gpt-5.6-terra",
        workspace=tmp_path,
        instructions=responses.CONTRACT,
        effort="low",
        pricing=Pricing(Decimal(2), Decimal(12), Decimal("0.2"), Decimal("2.5")),
    )
    harness = responses.ResponsesHarness(settings)
    harness.root = tmp_path / "native"
    harness.logs = tmp_path / "logs"
    await harness.start()
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(harness, "_start_sandbox", lambda: None)
    facts = {
        "workspace_head": "head",
        "diff_fingerprint": "diff",
        "changed_files": ["Window.svelte"],
    }
    monkeypatch.setattr(responses, "workspace_facts", AsyncMock(return_value=facts))
    check = {
        "kind": "frontend_checks",
        "paths": ["Window.svelte"],
        "exit_code": 0,
        "checks": [{"name": name, "exit_code": 0} for name in ("format", "typecheck", "lint")],
    }
    monkeypatch.setattr(harness, "_tool", lambda name, arguments: check)
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        if disconnect:
            raise httpx.ReadTimeout("uncertain", request=request)
        if len(requests) == 1:
            output = [
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "run_developer_checks",
                    "arguments": '{"paths":["Window.svelte"]}',
                }
            ]
        else:
            output = [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "IMPLEMENTED\nReady for validation"}
                    ],
                }
            ]
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": output,
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 500},
                    "output_tokens_details": {"reasoning_tokens": 10},
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(responses.httpx, "AsyncClient", lambda **kwargs: client)
    receipt = await harness.run_turn("Move and resize the window, not its contents")
    if disconnect:
        assert len(requests) == 1
        assert not receipt.usage.complete
        assert receipt.status == "interrupted"
    else:
        assert len(requests) == 2
        assert receipt.status == "completed"
        assert receipt.usage.input_tokens == 2000
        assert receipt.usage.cache_read_input_tokens == 1000
        assert receipt.token_efficiency["inference_cycle_count"] == 2
        assert receipt.token_efficiency["frontend_checks"]["diff_fingerprint"] == "diff"
        assert requests[1]["input"][-1]["type"] == "function_call_output"
