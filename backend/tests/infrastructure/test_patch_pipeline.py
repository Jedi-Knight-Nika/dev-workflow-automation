import hashlib
import json
import subprocess
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.domain.usage import Pricing
from app.agent_runtime.infrastructure import patch_pipeline
from app.agent_runtime.infrastructure.patch_tools import apply


def test_supervisor_selection_beats_lexical_document_and_keeps_linked_sources(
    tmp_path, monkeypatch
):
    from app.agent_runtime.infrastructure import patch_tools
    from app.supervisor.infrastructure.schemas import SupervisorDecision

    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "client/splash.html"
    target.parent.mkdir()
    target.write_text('<link href="theme.css"><script src="boot.js"></script>')
    (target.parent / "theme.css").write_text("body { color: red; }")
    (target.parent / "boot.js").write_text("const ready = true;")
    (tmp_path / "NOTES.md").write_text("old startup text " * 3000)
    decision = SupervisorDecision(
        action="DELEGATE_IMPLEMENTATION",
        task_class="STANDARD",
        confidence=0.8,
        assessment="Change startup appearance",
        execution_brief="Inspect startup UI",
        acceptance_criteria=[],
        unresolved_items=[],
        physical_object="startup window",
        operations=[],
        preserve=[],
        do_not_assume=[],
        target_paths=["client/splash.html"],
    )
    prompt = "old startup text" + decision.developer_guidance()
    packet = patch_tools.prepare(tmp_path, prompt)
    assert [s["path"] for s in packet["sources"]] == [
        "client/splash.html",
        "client/theme.css",
        "client/boot.js",
    ]
    decision.target_paths = ["../outside.html"]
    with pytest.raises(ValueError):
        patch_tools.prepare(tmp_path, "old startup text" + decision.developer_guidance())


def test_localization_uses_original_and_skips_oversized_related_file(tmp_path, monkeypatch):
    from app.agent_runtime.infrastructure import patch_tools

    names = ["frontend/src/Window.svelte", "frontend/src/Other.svelte"]
    for name, size in zip(names, [100, 40000], strict=True):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x" * size)

    def investigate(workspace, query, *, include_source_slices):
        assert query == "Move Window"
        assert include_source_slices is False
        return {"candidate_paths": names, "repo_map": [], "sha": "test"}

    monkeypatch.setattr(patch_tools, "investigate", investigate)
    packet = patch_tools.prepare(
        tmp_path,
        "Move Window\n\nTrello: https://example.test\nAdvisory Supervisor annotations noise",
    )
    assert [s["path"] for s in packet["sources"]] == names[:1]


def test_complete_patch_is_atomic_and_rejects_stale_or_outside_paths(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = tmp_path / "frontend/src/Window.svelte"
    path.parent.mkdir(parents=True)
    path.write_text("one\ntwo\nthree\n")
    name = str(path.relative_to(tmp_path))
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()}
    patch = f"--- a/{name}\n+++ b/{name}\n@@ -1,3 +1,3 @@\n-one\n+ONE\n two\n-three\n+THREE\n"
    with pytest.raises(ValueError):
        apply(tmp_path, patch.replace("two\n", "wrong\n"), hashes)
    assert path.read_text() == "one\ntwo\nthree\n"
    with pytest.raises(ValueError):
        apply(tmp_path, patch.replace(name, ".git/config"), hashes)
    assert apply(tmp_path, patch, hashes) == [name]
    assert path.read_text() == "ONE\ntwo\nTHREE\n"
    with pytest.raises(ValueError, match="changed"):
        apply(tmp_path, patch, hashes)


def test_plain_multifile_patch_with_recount_is_atomic(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    names = ["one.html", "two.css"]
    hashes = {}
    patches = []
    for name in names:
        path = tmp_path / name
        path.write_text("before\n")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        patches.append(f"--- a/{name}\n+++ b/{name}\n@@ -1,9 +1,9 @@\n-before\n+after\n")
    combined = "".join(patches)
    with pytest.raises(ValueError):
        apply(
            tmp_path, combined.replace(patches[1], patches[1].replace("-before", "-wrong")), hashes
        )
    assert all((tmp_path / n).read_text() == "before\n" for n in names)
    assert apply(tmp_path, combined, hashes) == names
    assert all((tmp_path / n).read_text() == "after\n" for n in names)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failures,expected_calls,expected_status",
    [(0, 1, "completed"), (1, 2, "completed"), (2, 2, "failed")],
)
async def test_one_patch_and_at_most_one_repair(
    tmp_path, monkeypatch, failures, expected_calls, expected_status
):
    settings = HarnessSettings(
        model="gpt-5.6-terra",
        workspace=tmp_path,
        instructions="original",
        effort="low",
        pricing=Pricing(Decimal(2), Decimal(12), Decimal("0.2"), Decimal("2.5")),
        supervision_callback=AsyncMock(),
    )
    harness = patch_pipeline.PatchPipelineHarness(settings)
    harness.root, harness.logs = tmp_path / "state", tmp_path / "logs"
    await harness.start()
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(harness, "_start_sandbox", lambda: None)
    path = "frontend/src/Window.svelte"
    facts = {"workspace_head": "head", "diff_fingerprint": "diff", "changed_files": [path]}
    monkeypatch.setattr(patch_pipeline, "workspace_facts", AsyncMock(return_value=facts))
    checks = 0

    async def operation(name, args):
        nonlocal checks
        if name == "prepare":
            return {
                "sources": [{"path": path, "sha256": "hash", "text": "original"}],
                "repo_map": [],
            }
        if name == "apply":
            return {"changed_files": [path]}
        checks += 1
        return {
            "exit_code": 1 if checks <= failures else 0,
            "paths": [path],
            "checks": [
                {
                    "name": "typecheck",
                    "exit_code": 1 if checks <= failures else 0,
                    "stdout_tail": "named type error",
                }
            ],
        }

    monkeypatch.setattr(harness, "operation", operation)
    requests = []

    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert "tools" not in payload
        assert payload["reasoning"]["effort"] == "low"
        assert len(payload["input"]) == 1
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "outcome": "PATCH",
                                        "summary": "Complete patch",
                                        "patch": "test patch",
                                    }
                                ),
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 10},
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(patch_pipeline.httpx, "AsyncClient", lambda **kwargs: client)
    receipt = await harness.run_turn("Move the window, not its contents")
    assert len(requests) == expected_calls
    assert receipt.status == expected_status
    assert receipt.usage.input_tokens == expected_calls * 1000
    settings.supervision_callback.assert_not_called()
    again = await harness.run_turn("retry")
    assert again.failure_code == "PATCH_ALREADY_ATTEMPTED"
    assert len(requests) == expected_calls
