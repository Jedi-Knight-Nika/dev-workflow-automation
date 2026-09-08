import hashlib
import json

import pytest

from app.agent_runtime.infrastructure.checkpoints import checkpoint_bytes, workspace_facts
from app.agent_runtime.infrastructure.process import capture
from app.agent_runtime.infrastructure.tool_logs import ToolLogs


@pytest.mark.asyncio
async def test_checkpoint_detects_tracked_and_untracked_edits_without_committing(tmp_path):
    await capture(["git", "init", str(tmp_path)])
    await capture(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "base",
        ],
        cwd=tmp_path,
    )
    first = await workspace_facts(tmp_path, tmp_path)
    (tmp_path / "new.py").write_text("first")
    second = await workspace_facts(tmp_path, tmp_path)
    assert first["workspace_head"] == second["workspace_head"]
    assert first["diff_fingerprint"] != second["diff_fingerprint"]
    assert second["changed_files"] == ["new.py"]
    (tmp_path / "new.py").write_text("second")
    assert (await workspace_facts(tmp_path, tmp_path))["diff_fingerprint"] != second[
        "diff_fingerprint"
    ]


def test_checkpoint_byte_cap_and_full_log_preservation(tmp_path):
    with pytest.raises(ValueError):
        checkpoint_bytes({"note": "x" * 5001})
    logs = ToolLogs(tmp_path)
    original = {"stdout": "x" * 20000, "stderr": "", "interrupted": False}
    result = logs.result("cmd", original, 4000)
    assert len(result["stdout"]) < 5000
    assert result["interrupted"] is False
    path = tmp_path / (hashlib.sha256(b"cmd").hexdigest() + ".log")
    assert json.loads(path.read_text()) == original
