import asyncio
import base64
import os
import re
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Integration, Repository, Task
from app.infrastructure.security.crypto import cipher
from app.integrations.github_auth import resolve_github_auth


class GitCommandError(RuntimeError):
    pass


def git_authorization_header(token: str) -> str:
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return f"Authorization: Basic {encoded}"


def task_branch(task: Task) -> str:
    source = task.external_key or str(task.id)[:8]
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", source).strip("-").lower()
    return f"agent/{slug}"


async def run_git(*args: str, cwd: Path | None = None, token: str | None = None) -> str:
    environment = os.environ.copy()
    if token:
        environment.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": git_authorization_header(token),
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise GitCommandError(stderr.decode(errors="replace")[-4000:])
    return stdout.decode(errors="replace").strip()


async def github_token(session: AsyncSession) -> str | None:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    if integration is None or integration.encrypted_credentials is None:
        return None
    auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
    return auth.token


async def prepare_repository_cache(session: AsyncSession, repository: Repository) -> Path:
    settings = get_settings()
    repositories_root = settings.workspace_root.resolve() / "_repositories"
    repositories_root.mkdir(parents=True, exist_ok=True)
    cache = repositories_root / str(repository.id)
    token = await github_token(session) if repository.provider == "github" else None
    if cache.exists() and not (cache / ".git").is_dir():
        shutil.rmtree(cache)
    if not cache.exists():
        await run_git("clone", "--no-checkout", repository.clone_url, str(cache), token=token)
    else:
        await run_git("fetch", "--prune", "origin", cwd=cache, token=token)
    repository.local_path = str(cache)
    repository.latest_sha = await run_git(
        "rev-parse", f"origin/{repository.default_branch}", cwd=cache
    )
    return cache


async def prepare_workspace(session: AsyncSession, task: Task, repository: Repository) -> Path:
    settings = get_settings()
    root = settings.workspace_root.resolve()
    worktrees_root = root / "tasks"
    worktrees_root.mkdir(parents=True, exist_ok=True)
    cache = await prepare_repository_cache(session, repository)
    workspace = worktrees_root / str(task.id)

    branch = task_branch(task)
    if not workspace.exists():
        await run_git(
            "worktree",
            "add",
            "-B",
            branch,
            str(workspace),
            f"origin/{repository.default_branch}",
            cwd=cache,
        )
    revision = await run_git("rev-parse", "HEAD", cwd=workspace)
    task.repository_id = repository.id
    task.branch_name = branch
    task.workspace_path = str(workspace)
    task.current_revision = revision
    await session.commit()
    return workspace
