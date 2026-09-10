"""No-model smoke: execute with isolated writable /workspace and /home/runner tmpfs.

Mount the frontend read-only at /fixtures. This never changes a real task checkout.
"""

import json
import shutil
from pathlib import Path

from openai_codex.client import CodexClient, CodexConfig
from openai_codex.generated.v2_all import CommandExecResponse, ThreadStartResponse

from app.agent_runtime.infrastructure.repo_index import investigate

workspace = Path("/workspace")
frontend = workspace / "frontend"
frontend.mkdir()
for name in (
    "package.json",
    ".prettierrc",
    "eslint.config.js",
    "svelte.config.js",
    "tsconfig.json",
):
    shutil.copyfile(Path("/fixtures") / name, frontend / name)
shutil.copytree("/opt/frontend/node_modules", frontend / "node_modules", symlinks=True)
(frontend / "src/lib").mkdir(parents=True)
(frontend / "src/app.html").write_text(
    '<!doctype html><html lang="en"><head>%sveltekit.head%</head><body><div>%sveltekit.body%</div></body></html>'
)
(frontend / "src/lib/Window.svelte").write_text("<script>const count = 0;</script><p>{count}</p>\n")
(frontend / "window.test.ts").write_text(
    "import {test, expect} from 'vitest'; test('runtime', () => expect(1+1).toBe(2));\n"
)
(frontend / "vitest.config.ts").write_text("export default {test:{include:['window.test.ts']}};\n")
logs = Path.home() / ".aew/tool-logs"
logs.mkdir(parents=True)
command = [
    "/app/.venv/bin/python",
    "-m",
    "app.agent_runtime.infrastructure.repository_tools",
    "check",
    "frontend/src/lib/Window.svelte",
]
client = CodexClient(CodexConfig(cwd=str(workspace)))
try:
    client.start()
    client.initialize()
    thread = client.request(
        "thread/start",
        {
            "cwd": str(workspace),
            "model": "gpt-5.6-terra",
            "ephemeral": True,
            "sandbox": "workspace-write",
            "approvalPolicy": "never",
            "config": {
                "sandbox_workspace_write.writable_roots": [str(logs)],
                "sandbox_workspace_write.network_access": False,
            },
        },
        response_model=ThreadStartResponse,
    )
    policy = thread.sandbox.model_dump(mode="json", by_alias=True)
    assert str(logs) in policy["writableRoots"], policy
    result = client.request(
        "command/exec",
        {
            "command": command,
            "cwd": str(workspace),
            "sandboxPolicy": policy,
            "timeoutMs": 45000,
        },
        response_model=CommandExecResponse,
    )
    check = client.request(
        "command/exec",
        {
            "command": [
                "/app/.venv/bin/python",
                "-m",
                "app.agent_runtime.infrastructure.bounded_command",
                "--",
                "./node_modules/.bin/vitest",
                "run",
                "--config",
                "vitest.config.ts",
            ],
            "cwd": str(frontend),
            "sandboxPolicy": policy,
            "timeoutMs": 45000,
        },
        response_model=CommandExecResponse,
    )
finally:
    client.close()
print(result.stdout)
if result.exit_code:
    print(result.stderr)
assert result.exit_code == 0, "Native sandbox formatting/logging failed"
receipt = json.loads(result.stdout)
assert receipt["exit_code"] == 0
assert len(receipt["checks"]) == 3
assert all(Path(row["full_log_path"]).is_file() for row in receipt["checks"])
assert "const count" in (frontend / "src/lib/Window.svelte").read_text()
assert check.exit_code == 0, check.stdout + check.stderr
mapped = investigate(workspace, "Window count")
assert "frontend/src/lib/Window.svelte" in mapped["candidate_paths"]
assert any(s["name"] == "count" for r in mapped["repo_map"] for s in r["symbols"])
print(
    "PASS: native sandbox, combined format/typecheck/file-lint, writable logs, targeted Vitest, Tree-sitter; no model calls"
)

# Exercise the Responses harness's actual sandbox/CLI boundary, not a mock.
from app.agent_runtime.application.harness import HarnessSettings
from app.agent_runtime.infrastructure.responses import ResponsesHarness

experiment = ResponsesHarness(
    HarnessSettings(model="gpt-5.6-terra", workspace=workspace, instructions="test")
)
try:
    experiment._start_sandbox()
    located = experiment._tool("repo_investigate", json.dumps({"objective": "Window count"}))
    assert "frontend/src/lib/Window.svelte" in located["candidate_paths"], located
    inspected = experiment._tool(
        "inspect_ranges",
        json.dumps({"ranges": [{"path": "frontend/src/lib/Window.svelte", "start": 1, "end": 30}]}),
    )
    edited = experiment._tool(
        "edit_file",
        json.dumps(
            {
                "path": "frontend/src/lib/Window.svelte",
                "sha256": inspected[0]["sha256"],
                "old_text": "const count = 0",
                "new_text": "const count = 1",
            }
        ),
    )
    assert edited["edited"] == "frontend/src/lib/Window.svelte", edited
    checked = experiment._tool(
        "run_developer_checks", json.dumps({"paths": ["frontend/src/lib/Window.svelte"]})
    )
    assert checked["exit_code"] == 0, checked
finally:
    if experiment.client:
        experiment.client.close()
print(
    "PASS: Responses compound investigation, inspection, exact edit and internally awaited checks; no model calls"
)

from app.agent_runtime.infrastructure.patch_pipeline import PatchPipelineHarness

patcher = PatchPipelineHarness(
    HarnessSettings(model="gpt-5.6-terra", workspace=workspace, instructions="test")
)
try:
    patcher._start_sandbox()
    packet = patcher._tool("prepare", json.dumps({"objective": "Window count"}))
    selected = packet["sources"][0]
    assert selected["path"] == "frontend/src/lib/Window.svelte", packet
    import difflib

    patch = "".join(
        difflib.unified_diff(
            selected["text"].splitlines(keepends=True),
            selected["text"]
            .replace("const count = 1", "const count = 2")
            .splitlines(keepends=True),
            fromfile="a/" + selected["path"],
            tofile="b/" + selected["path"],
        )
    )
    applied = patcher._tool(
        "apply", json.dumps({"patch": patch, "hashes": {selected["path"]: selected["sha256"]}})
    )
    assert applied["changed_files"] == [selected["path"]], applied
    checked = patcher._tool("check", json.dumps({"paths": applied["changed_files"]}))
    assert checked["exit_code"] == 0, checked
finally:
    if patcher.client:
        patcher.client.close()
print("PASS: deterministic localization, whole unified patch, combined checks; zero model calls")
