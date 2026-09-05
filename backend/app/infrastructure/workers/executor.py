import asyncio
import hashlib
import json
import os
import signal
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.infrastructure.git.workspaces import run_git

MAX_CONTEXT_BYTES = 120_000
MAX_FILE_BYTES = 40_000


class FileWrite(BaseModel):
    path: str
    content: str


class ExecutorProposal(BaseModel):
    result: Literal["IMPLEMENTED", "PLAN_MISMATCH", "BLOCKED", "NEEDS_REPLAN", "NEEDS_HUMAN"] = (
        "IMPLEMENTED"
    )
    summary: str
    files: list[FileWrite] = Field(default_factory=list)
    delete_files: list[str] = Field(default_factory=list)
    plan_mismatch: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "ExecutorProposal":
        if self.result != "IMPLEMENTED" and (self.files or self.delete_files):
            raise ValueError(f"{self.result} must not include file changes")
        if self.result in {"PLAN_MISMATCH", "NEEDS_REPLAN"} and not self.plan_mismatch:
            raise ValueError(f"{self.result} requires plan_mismatch details")
        if self.result in {"BLOCKED", "NEEDS_HUMAN"} and not self.reason:
            raise ValueError(f"{self.result} requires a reason")
        return self


class CheckResult(BaseModel):
    command: list[str]
    passed: bool
    output: str


class ReviewFinding(BaseModel):
    severity: str
    path: str | None = None
    line: int | None = None
    message: str


class ReviewerProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["PASS", "FAIL_ACTIONABLE", "FAIL_ARCHITECTURAL", "UNCERTAIN", "NEEDS_HUMAN"]
    summary: str
    findings: list[ReviewFinding] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "ReviewerProposal":
        if self.result == "PASS" and self.findings:
            raise ValueError("PASS must not include findings")
        if self.result in {"FAIL_ACTIONABLE", "FAIL_ARCHITECTURAL"} and not self.findings:
            raise ValueError(f"{self.result} requires at least one finding")
        if self.result in {"UNCERTAIN", "NEEDS_HUMAN"} and not self.reason:
            raise ValueError(f"{self.result} requires a reason")
        return self


def credential_subprocess_environment(values: dict[str, str]) -> dict[str, str]:
    allowed = {
        "NODE_AUTH_TOKEN",
        "NPM_CONFIG_REGISTRY",
        "UV_INDEX_USERNAME",
        "UV_INDEX_PASSWORD",
        "UV_DEFAULT_INDEX",
    }
    return {key: value for key, value in values.items() if key in allowed}


def redact_credentials(output: str, values: dict[str, str]) -> str:
    secrets = [value for key, value in values.items() if key.endswith(("TOKEN", "PASSWORD"))]
    for secret in secrets:
        if secret:
            output = output.replace(secret, "[REDACTED]")
    return output


def _safe_path(workspace: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"Unsafe workspace path: {relative}")
    resolved = (workspace / Path(*candidate.parts)).resolve()
    if not resolved.is_relative_to(workspace.resolve()):
        raise ValueError(f"Path escapes workspace: {relative}")
    return resolved


async def repository_context(workspace: Path) -> str:
    tracked = (await run_git("ls-files", cwd=workspace)).splitlines()
    sections: list[str] = []
    used = 0
    for relative in tracked:
        path = _safe_path(workspace, relative)
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        section = f"\n--- FILE: {relative} ---\n{content}"
        size = len(section.encode())
        if used + size > MAX_CONTEXT_BYTES:
            continue
        sections.append(section)
        used += size
    return "".join(sections)


def apply_proposal(workspace: Path, proposal: ExecutorProposal) -> None:
    for change in proposal.files:
        path = _safe_path(workspace, change.path)
        if path.exists() and path.is_symlink():
            raise ValueError(f"Refusing to replace symlink: {change.path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(change.content, encoding="utf-8")
    for relative in proposal.delete_files:
        path = _safe_path(workspace, relative)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Refusing unsafe deletion: {relative}")
        path.unlink()


def detected_checks(workspace: Path) -> list[list[str]]:
    checks: list[list[str]] = []
    if (workspace / "package.json").exists():
        package = json.loads((workspace / "package.json").read_text())
        scripts = package.get("scripts", {})
        if isinstance(scripts, dict):
            for name in ("check", "lint", "test"):
                if name in scripts:
                    checks.append(["npm", "run", name])
    if (workspace / "pyproject.toml").exists():
        checks.extend([["uv", "run", "ruff", "check", "."], ["uv", "run", "pytest", "-q"]])
    return checks


def dependency_setup_commands(workspace: Path) -> list[list[str]]:
    commands: list[list[str]] = []
    if (workspace / "package-lock.json").exists():
        commands.append(["npm", "ci"])
    if (workspace / "uv.lock").exists():
        commands.append(["uv", "sync", "--frozen", "--all-extras"])
    return commands


async def run_checks(
    workspace: Path,
    timeout_seconds: int = 180,
    credential_environment: dict[str, str] | None = None,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    setup_commands = dependency_setup_commands(workspace)
    commands = setup_commands + detected_checks(workspace)
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": "/tmp/worker-home",
            "NPM_CONFIG_CACHE": "/tmp/npm-cache",
            "UV_CACHE_DIR": "/tmp/uv-cache",
            "XDG_CACHE_HOME": "/tmp/xdg-cache",
        }
    )
    supplied = credential_environment or {}
    for command in commands:
        process: asyncio.subprocess.Process | None = None
        try:
            command_environment = environment.copy()
            if command in setup_commands:
                command_environment.update(credential_subprocess_environment(supplied))
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=workspace,
                env=command_environment,
                start_new_session=True,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            output = stdout.decode(errors="replace")[-6000:]
            output = redact_credentials(output, supplied)
            passed = process.returncode == 0
            results.append(CheckResult(command=command, passed=passed, output=output))
            if not passed and command in setup_commands:
                break
        except TimeoutError:
            if process is not None:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            results.append(CheckResult(command=command, passed=False, output="Command timed out"))
            break
        except FileNotFoundError as exc:
            results.append(CheckResult(command=command, passed=False, output=str(exc)))
            if command in setup_commands:
                break
    return results


async def changed_files(workspace: Path) -> list[str]:
    output = await run_git("status", "--short", cwd=workspace)
    return [line[3:] for line in output.splitlines() if len(line) > 3]


async def workspace_fingerprint(workspace: Path) -> str:
    diff = await run_git("diff", "--binary", "--no-ext-diff", cwd=workspace)
    return hashlib.sha256(diff.encode()).hexdigest()
