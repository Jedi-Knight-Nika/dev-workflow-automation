"""Controller-generated Git facts; semantic notes cannot supply authoritative state."""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.agent_runtime.infrastructure.process import capture


async def workspace_facts(workspace: Path, root: Path) -> dict[str, Any]:
    workspace = workspace.resolve(strict=True)
    if not workspace.is_relative_to(root.resolve()):
        raise ValueError("Checkpoint workspace is outside the task root")

    async def git(*args: str) -> bytes:
        return await capture(
            [
                "git",
                "-c",
                "safe.directory=" + str(workspace),
                "-c",
                "core.hooksPath=/dev/null",
                "--no-optional-locks",
                *args,
            ],
            cwd=workspace,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0",
            },
            timeout=10,
            output_limit=2_000_000,
        )

    head = (await git("rev-parse", "HEAD")).decode().strip()
    tracked = await git("diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--")
    names = await git("diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", "HEAD", "--")
    untracked = await git("ls-files", "--others", "--exclude-standard", "-z")
    digest = hashlib.sha256(head.encode() + tracked)
    changed = sorted({n.decode() for n in (names + untracked).split(b"\0") if n})
    if len(changed) > 200:
        raise ValueError("Checkpoint has too many changed files")
    size = 0
    for name in sorted(n.decode() for n in untracked.split(b"\0") if n):
        path = workspace / name
        if path.is_symlink() or not path.resolve().is_relative_to(workspace) or not path.is_file():
            raise ValueError("Checkpoint cannot verify an untracked special file")
        size += path.stat().st_size
        if size > 20_000_000:
            raise ValueError("Untracked checkpoint content exceeds its verification bound")
        digest.update(name.encode() + b"\0" + path.read_bytes())
    return {
        "workspace_head": head,
        "diff_fingerprint": digest.hexdigest(),
        "changed_files": changed,
    }


def checkpoint_bytes(value: dict[str, Any]) -> bytes:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    # Byte cap is conservative even for an unknown tokenizer (<= 5k token bytes).
    if len(data) > 5000:
        raise ValueError("Checkpoint exceeds its 5,000-byte hard bound; shorten the note")
    return data
