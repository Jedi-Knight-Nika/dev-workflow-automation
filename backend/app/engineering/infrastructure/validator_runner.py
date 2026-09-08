"""Deterministic test/commit boundary inside a credential-free container."""

import asyncio
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.agent_runtime.infrastructure.process import capture
from app.agent_runtime.infrastructure.workspace_lock import workspace_lock
from app.engineering.infrastructure.validation import run_check


class ValidationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch: str = Field(min_length=1, max_length=255, pattern=r"^agent/[a-zA-Z0-9._/-]+$")
    title: str = Field(min_length=1, max_length=500)
    author_name: str = Field(min_length=1, max_length=120)
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    commands: list[list[str]] = Field(min_length=1, max_length=12)
    timeout_seconds: int = Field(default=1200, ge=1, le=7200)


async def git(*args: str) -> str:
    stdout = await capture(
        ("git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args),
        output_limit=2 * 1024**2,
    )
    return stdout.decode() if "-z" in args else stdout.decode().strip()


def workspace_fingerprint(paths: str) -> str:
    digest = hashlib.sha256()
    for name in sorted(set(paths.split("\0"))):
        if not name:
            continue
        path = Path(name)
        digest.update(name.encode())
        if path.is_symlink():
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(65536), b""):
                    digest.update(block)
        else:
            digest.update(b"MISSING")
    return digest.hexdigest()


async def validate(manifest: ValidationManifest) -> dict[str, object]:
    if os.getuid() != 10001 or Path.cwd() != Path("/workspace"):
        raise RuntimeError("Validation must run in the dedicated non-root container")
    if any(
        os.environ.get(key)
        for key in (
            "DATABASE_URL",
            "APP_SECRET_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GITHUB_TOKEN",
        )
    ):
        raise RuntimeError("Validation cannot receive credentials")
    if await git("branch", "--show-current") != manifest.branch:
        raise ValueError("Workspace changed branches")
    paths_before = await git("ls-files", "-c", "-o", "--exclude-standard", "-z")
    before = workspace_fingerprint(paths_before)
    checks = []
    for command in manifest.commands:
        if not command or any(not arg or len(arg) > 1000 for arg in command):
            raise ValueError("Invalid validation command")
        checks.append(
            await run_check(
                tuple(command),
                workspace=Path("/workspace"),
                timeout=manifest.timeout_seconds,
                output_limit=8000,
            )
        )
    passed = all(check.passed for check in checks)
    after_paths = await git("ls-files", "-c", "-o", "--exclude-standard", "-z")
    if passed and workspace_fingerprint(after_paths) != before:
        # Test generators must not make unvalidated source changes part of a passing commit.
        raise ValueError("Validation changed repository files; review before publication")
    if passed and await git("status", "--porcelain"):
        await git("add", "--all")
        await git(
            "-c",
            f"user.name={manifest.author_name}",
            "-c",
            "user.email=engineering-worker@localhost",
            "commit",
            "-m",
            manifest.title[:72],
        )
    paths = await git("ls-files", "-c", "-o", "--exclude-standard", "-z")
    return {
        "passed": passed,
        "head_sha": await git("rev-parse", "HEAD"),
        "fingerprint": workspace_fingerprint(paths),
        "checks": [asdict(check) for check in checks],
        "change_context": (
            await git(
                "diff", "--no-ext-diff", "--no-textconv", "--stat", manifest.base_sha, "HEAD", "--"
            )
        )[:6000],
    }


def main() -> None:
    try:
        path = Path("/run/control/task.json")
        if path.stat().st_size > 64000:
            raise ValueError("Validation manifest too large")
        with workspace_lock():
            result = asyncio.run(
                validate(ValidationManifest.model_validate_json(path.read_bytes()))
            )
        print(json.dumps(result), flush=True)
    except Exception as exc:  # noqa: BLE001 - no raw subprocess errors cross the container boundary
        print(json.dumps({"failure_code": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
