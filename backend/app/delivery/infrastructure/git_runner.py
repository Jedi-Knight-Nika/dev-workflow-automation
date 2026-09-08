"""Short-lived Git-only runner. Never executes repository code or loads its config.

Publication copies Git objects into a new bare database; task-controlled remotes,
hooks, includes, filters and credential helpers never enter the credentialed Git.
"""

import asyncio
import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent_runtime.infrastructure.process import capture
from app.agent_runtime.infrastructure.workspace_lock import workspace_lock


class GitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["prepare", "publish"]
    owner: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,99}$")
    repository: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    branch: str = Field(pattern=r"^agent/task-[0-9a-f-]{36}$")
    base_branch: str = Field(min_length=1, max_length=255)
    expected_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40,64}$")


async def git(directory: Path, *args: str, token: str | None = None) -> str:
    environment = {
        "PATH": os.defpath,
        "HOME": "/tmp",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "5",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null",
        "GIT_CONFIG_KEY_1": "core.fsmonitor",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "credential.helper",
        "GIT_CONFIG_VALUE_2": "",
        "GIT_CONFIG_KEY_3": "protocol.file.allow",
        "GIT_CONFIG_VALUE_3": "never",
        "GIT_CONFIG_KEY_4": "http.followRedirects",
        "GIT_CONFIG_VALUE_4": "false",
    }
    for key in ("HTTP_PROXY", "HTTPS_PROXY"):
        if os.environ.get(key):
            environment[key] = os.environ[key]
    if token:
        environment.update(
            {
                "GIT_CONFIG_COUNT": "6",
                "GIT_CONFIG_KEY_5": "http.https://github.com/.extraHeader",
                "GIT_CONFIG_VALUE_5": "Authorization: Basic "
                + base64.b64encode(f"x-access-token:{token}".encode()).decode(),
            }
        )
    output = await capture(
        ("git", *args),
        cwd=directory,
        env=environment,
    )
    return output.decode().strip()


def copy_objects(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Standalone Git objects required")
    size = 0
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("Git object symlinks are not allowed")
        if path.is_file():
            size += path.stat().st_size
            if size > 2 * 1024**3:
                raise ValueError("Git object transfer exceeds the 2 GiB safety bound")
            relative = path.relative_to(source)
            # Do not transfer alternates, grafts, refs or any task configuration.
            if relative.parts[0] == "info":
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


async def execute(manifest: GitManifest, workspace: Path = Path("/workspace")) -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("A short-lived GitHub credential is required")
    url = f"https://github.com/{manifest.owner}/{manifest.repository}.git"
    await git(Path("/tmp"), "check-ref-format", "--branch", manifest.base_branch)
    if manifest.operation == "prepare":
        if any(workspace.iterdir()):
            raise ValueError("Preparation refuses to overwrite an existing workspace")
        await git(workspace, "init", "--initial-branch", manifest.branch, ".")
        await git(
            workspace, "fetch", "--no-tags", url, f"refs/heads/{manifest.base_branch}", token=token
        )
        await git(workspace, "checkout", "-B", manifest.branch, "FETCH_HEAD")
        sha = await git(workspace, "rev-parse", "HEAD")
        # No remote or credential is persisted in .git/config.
        return {"head_sha": sha}
    if not manifest.expected_sha:
        raise ValueError("Publication requires the validated revision")
    git_dir = workspace / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        raise ValueError("An isolated Git database is required")
    with tempfile.TemporaryDirectory(prefix="publish-") as directory:
        bare = Path(directory)
        await git(bare, "init", "--bare", ".")
        copy_objects(git_dir / "objects", bare / "objects")
        await git(bare, "cat-file", "-e", f"{manifest.expected_sha}^{{commit}}")
        await git(bare, "fsck", "--no-reflogs", "--no-dangling", manifest.expected_sha)
        # A normal fast-forward push, never --force. Idempotent at the same SHA.
        await git(
            bare, "push", url, f"{manifest.expected_sha}:refs/heads/{manifest.branch}", token=token
        )
    return {"head_sha": manifest.expected_sha}


def main() -> None:
    if os.getuid() != 10001:
        raise RuntimeError("Git runner must be non-root")
    if any(
        os.environ.get(key)
        for key in ("DATABASE_URL", "APP_SECRET_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    ):
        raise RuntimeError("Unexpected credentials in Git runner")
    manifest = GitManifest.model_validate_json(Path("/run/control/task.json").read_bytes())
    with workspace_lock(Path("/run/workspace.lock")):
        print(json.dumps(asyncio.run(execute(manifest))), flush=True)


if __name__ == "__main__":
    main()
