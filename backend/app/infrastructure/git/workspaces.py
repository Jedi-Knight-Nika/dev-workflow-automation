import asyncio
import base64
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    Integration,
    Repository,
    Task,
    TaskRepositoryScope,
    TaskState,
    WorkspaceLease,
)
from app.infrastructure.security.crypto import cipher
from app.integrations.github_auth import resolve_github_auth

from .locking import repository_lock


class GitCommandError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScopedWorkspace:
    scope: TaskRepositoryScope
    repository: Repository
    path: Path


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
    async with repository_lock(session, repository.id):
        return await _prepare_repository_cache(session, repository)


async def _prepare_repository_cache(session: AsyncSession, repository: Repository) -> Path:
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
    async with repository_lock(session, repository.id):
        cache = await _prepare_repository_cache(session, repository)
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


async def prepare_task_workspaces(session: AsyncSession, task: Task) -> list[ScopedWorkspace]:
    """Prepare every AI-selected repository without sharing mutable worktrees."""
    scope_rows = (
        await session.execute(
            select(TaskRepositoryScope, Repository)
            .join(Repository, Repository.id == TaskRepositoryScope.repository_id)
            .where(TaskRepositoryScope.task_id == task.id, Repository.enabled.is_(True))
            .order_by(TaskRepositoryScope.is_primary.desc(), TaskRepositoryScope.created_at)
        )
    ).all()
    if not scope_rows:
        if task.repository_id is None:
            return []
        repository = await session.get(Repository, task.repository_id)
        if repository is None or not repository.enabled:
            return []
        return [
            ScopedWorkspace(
                TaskRepositoryScope(task_id=task.id, repository_id=repository.id),
                repository,
                await prepare_workspace(session, task, repository),
            )
        ]

    root = get_settings().workspace_root.resolve() / "tasks" / str(task.id)
    legacy_workspace = Path(task.workspace_path) if task.workspace_path else None
    prepared: list[ScopedWorkspace] = []
    for scope, repository in scope_rows:
        if scope.workspace_path and Path(scope.workspace_path).is_dir():
            workspace = Path(scope.workspace_path)
        elif len(scope_rows) == 1 and legacy_workspace and (legacy_workspace / ".git").exists():
            workspace = legacy_workspace
        else:
            root.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", repository.name).strip("-").lower()
            workspace = root / f"{slug}-{str(repository.id)[:8]}"
            async with repository_lock(session, repository.id):
                cache = await _prepare_repository_cache(session, repository)
                if not workspace.exists():
                    await run_git(
                        "worktree",
                        "add",
                        "-B",
                        task_branch(task),
                        str(workspace),
                        f"origin/{repository.default_branch}",
                        cwd=cache,
                    )
        revision = await run_git("rev-parse", "HEAD", cwd=workspace)
        scope.workspace_path = str(workspace)
        scope.branch_name = task_branch(task)
        scope.base_revision = scope.base_revision or revision
        scope.current_revision = revision
        prepared.append(ScopedWorkspace(scope, repository, workspace))

    primary = prepared[0]
    task.repository_id = primary.repository.id
    task.branch_name = primary.scope.branch_name
    task.workspace_path = str(root) if len(prepared) > 1 else str(primary.path)
    task.current_revision = primary.scope.current_revision
    await session.commit()
    return prepared


async def cleanup_archived_workspaces(
    session: AsyncSession,
    workspace_root: Path,
    completed_retention_days: int,
    failed_retention_days: int | None = None,
) -> int:
    """Remove only old, archived, clean worktrees that have no active lease."""
    completed_cutoff = datetime.now(UTC) - timedelta(days=completed_retention_days)
    failed_cutoff = datetime.now(UTC) - timedelta(
        days=failed_retention_days or completed_retention_days
    )
    tasks = list(
        (
            await session.scalars(
                select(Task).where(
                    Task.archived_at.is_not(None),
                    or_(
                        (Task.state == TaskState.MERGED) & (Task.archived_at <= completed_cutoff),
                        Task.state.in_((TaskState.CANCELLED, TaskState.FAILED))
                        & (Task.archived_at <= failed_cutoff),
                    ),
                    Task.workspace_path.is_not(None),
                    ~exists().where(WorkspaceLease.task_id == Task.id),
                )
            )
        ).all()
    )
    tasks_root = (workspace_root.resolve() / "tasks").resolve()
    removed = 0
    for task in tasks:
        workspace = Path(task.workspace_path or "").resolve()
        if not workspace.is_relative_to(tasks_root):
            continue
        scope_rows = (
            await session.execute(
                select(TaskRepositoryScope, Repository)
                .join(Repository, Repository.id == TaskRepositoryScope.repository_id)
                .where(
                    TaskRepositoryScope.task_id == task.id,
                    TaskRepositoryScope.workspace_path.is_not(None),
                )
            )
        ).all()
        if workspace.exists() and len(scope_rows) <= 1:
            try:
                if await run_git("status", "--porcelain", cwd=workspace):
                    continue
            except GitCommandError:
                continue
        repository = (
            await session.get(Repository, task.repository_id) if task.repository_id else None
        )
        try:
            if len(scope_rows) > 1:
                for scope, scoped_repository in scope_rows:
                    scoped_workspace = Path(scope.workspace_path or "").resolve()
                    if not scoped_workspace.is_relative_to(tasks_root):
                        continue
                    if scoped_workspace.exists() and await run_git(
                        "status", "--porcelain", cwd=scoped_workspace
                    ):
                        raise GitCommandError("Scoped workspace contains uncommitted changes")
                    if scoped_repository.local_path and scoped_workspace.exists():
                        cache = Path(scoped_repository.local_path).resolve()
                        async with repository_lock(session, scoped_repository.id):
                            await run_git(
                                "worktree",
                                "remove",
                                "--force",
                                str(scoped_workspace),
                                cwd=cache,
                            )
                    scope.workspace_path = None
                if workspace.exists():
                    shutil.rmtree(workspace)
            elif workspace.exists() and repository is not None and repository.local_path:
                cache = Path(repository.local_path).resolve()
                repositories_root = (workspace_root.resolve() / "_repositories").resolve()
                if not cache.is_relative_to(repositories_root):
                    continue
                async with repository_lock(session, repository.id):
                    await run_git("worktree", "remove", "--force", str(workspace), cwd=cache)
            elif workspace.exists():
                shutil.rmtree(workspace)
        except GitCommandError:
            continue
        task.workspace_path = None
        removed += 1
    if removed:
        await session.commit()
    return removed
