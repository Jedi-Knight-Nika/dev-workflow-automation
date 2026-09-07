"""Reuse validated plans only for identical planning inputs and workspace contents."""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.infrastructure.git.workspaces import run_git


async def clean_workspace_revisions(workspaces: list[tuple[str, Path]]) -> dict[str, str] | None:
    """A dirty checkout cannot safely reuse a source-based planning result."""
    revisions: dict[str, str] = {}
    for repository_id, path in workspaces:
        if await run_git("status", "--porcelain", "--untracked-files=all", cwd=path):
            return None
        revisions[repository_id] = await run_git("rev-parse", "HEAD", cwd=path)
    return revisions


def plan_input_fingerprint(
    context: dict[str, Any], runtime: dict[str, Any], workspaces: dict[str, str]
) -> str:
    value = json.loads(json.dumps(context))
    value.pop("previous_role_checkpoint", None)
    value.get("task", {}).pop("state", None)
    value.get("job", {}).pop("id", None)
    memory = value.get("task_memory", {})
    memory.pop("memory_version", None)
    memory.pop("current_plan_job_id", None)
    material = {"context": value, "runtime": runtime, "workspaces": workspaces, "version": 1}
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
