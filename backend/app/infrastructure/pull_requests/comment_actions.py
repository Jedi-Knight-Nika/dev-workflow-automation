from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.intake_completion import IntakeCompletionContext
from app.application.pull_requests import MergeConflict, MergeTask, MergeUnavailable
from app.db.models import Integration, Repository, Task, TaskState
from app.infrastructure.git.workspaces import GitCommandError, github_token, run_git
from app.infrastructure.integration_access import role_allows_integration
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.pull_requests.merge_workflow import SqlAlchemyGitHubMergeWorkflow
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth

_AUTHORIZED_PERMISSIONS = {"admin", "maintain", "write"}


class GitHubCommentActionExecutor:
    """Executes a small, audited command set requested through a GitHub PR comment."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute(self, context: IntakeCompletionContext) -> None:
        actions = self._actions(context)
        if not actions:
            return
        task = await self._session.get(Task, context.task_id)
        if task is None or task.repository_id is None or task.pull_request_number is None:
            await self._reject(context.task_id, "Task has no active pull request")
            return
        repository = await self._session.get(Repository, task.repository_id)
        integration = await self._session.scalar(
            select(Integration).where(Integration.provider_name == "github")
        )
        if repository is None or integration is None or integration.encrypted_credentials is None:
            await self._reject(task.id, "GitHub integration is unavailable")
            return
        if not await role_allows_integration(self._session, "DELIVERER", integration.id):
            await self._reject(task.id, "GitHub is not enabled for delivery")
            return

        client = await self._client(integration)
        actor = str(context.job_payload.get("author") or "").strip()
        if not actor or not await self._is_authorized(client, repository, actor):
            await self._reject(task.id, "Comment author cannot administer this pull request")
            return

        title = self._value(actions, "UPDATE_PR_TITLE")
        body = self._value(actions, "UPDATE_PR_BODY")
        commit_message = self._value(actions, "UPDATE_COMMIT_MESSAGE")
        if commit_message is not None and not await self._rewrite_commit(
            task, commit_message, actor
        ):
            return
        if title is not None or body is not None:
            try:
                await client.update_pull_request(
                    repository.owner,
                    repository.name,
                    task.pull_request_number,
                    title=title,
                    body=body,
                )
            except Exception:  # noqa: BLE001 - turn provider details into a safe audit event
                await self._reject(task.id, "GitHub rejected the pull-request metadata update")
                return
            await record_event(
                self._session,
                task.id,
                "PULL_REQUEST_METADATA_UPDATED",
                {
                    "actor": actor,
                    "fields": [
                        field
                        for field, value in (("title", title), ("body", body))
                        if value is not None
                    ],
                    "source_url": context.job_payload.get("url"),
                },
            )
            await self._session.commit()

        if any(action.get("action") == "MERGE_PULL_REQUEST" for action in actions):
            await record_event(
                self._session,
                task.id,
                "PULL_REQUEST_MERGE_REQUESTED",
                {"actor": actor, "source_url": context.job_payload.get("url")},
            )
            await self._session.commit()
            await self._merge(task.id, actor, context.job_payload.get("url"))

    @staticmethod
    def _actions(context: IntakeCompletionContext) -> list[dict[str, Any]]:
        if (
            context.action != "INTERPRET_EXTERNAL_COMMENT"
            or context.job_payload.get("source") != "github"
        ):
            return []
        raw = context.data.get("external_delivery_actions")
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    async def _client(self, integration: Integration) -> GitHubClient:
        credentials = cipher.decrypt(integration.encrypted_credentials or b"")
        auth = await resolve_github_auth(credentials)
        return GitHubClient(auth.token, auth.installation)

    @staticmethod
    async def _is_authorized(client: GitHubClient, repository: Repository, actor: str) -> bool:
        try:
            permission = await client.collaborator_permission(
                repository.owner, repository.name, actor
            )
        except Exception:  # noqa: BLE001 - absence/error must fail closed
            return False
        return permission in _AUTHORIZED_PERMISSIONS

    @staticmethod
    def _value(actions: list[dict[str, Any]], action_name: str) -> str | None:
        matching = [item for item in actions if item.get("action") == action_name]
        if not matching:
            return None
        value = matching[-1].get("value")
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    async def _merge(self, task_id: Any, actor: str, source_url: object) -> None:
        try:
            await MergeTask(SqlAlchemyGitHubMergeWorkflow(self._session)).execute(task_id)
        except (MergeConflict, MergeUnavailable, ValueError) as exc:
            await record_event(
                self._session,
                task_id,
                "PULL_REQUEST_MERGE_DEFERRED",
                {
                    "actor": actor,
                    "reason": str(exc),
                    "source_url": source_url,
                },
            )
            await self._session.commit()

    async def _rewrite_commit(self, task: Task, message: str, actor: str) -> bool:
        if not task.workspace_path or not task.branch_name or not task.current_revision:
            await self._reject(task.id, "Task branch is unavailable for commit-message update")
            return False
        workspace = Path(task.workspace_path)
        try:
            old_revision = await run_git("rev-parse", "HEAD", cwd=workspace)
            if old_revision != task.current_revision:
                await self._reject(task.id, "Task branch revision changed before commit update")
                return False
            await run_git(
                "-c",
                "user.name=Engineering Worker",
                "-c",
                "user.email=engineering-worker@localhost",
                "commit",
                "--amend",
                "-m",
                message,
                cwd=workspace,
            )
            new_revision = await run_git("rev-parse", "HEAD", cwd=workspace)
            token = await github_token(self._session)
            if token is None:
                raise GitCommandError("GitHub credentials are unavailable")
            await run_git(
                "push",
                f"--force-with-lease=refs/heads/{task.branch_name}:{old_revision}",
                "origin",
                f"HEAD:refs/heads/{task.branch_name}",
                cwd=workspace,
                token=token,
            )
        except (GitCommandError, OSError):
            try:
                await run_git("reset", "--soft", task.current_revision, cwd=workspace)
            except (GitCommandError, OSError):
                pass
            await self._reject(task.id, "Commit-message update could not be pushed safely")
            return False
        task.current_revision = new_revision
        task.state = TaskState.WAITING_GITHUB
        await record_event(
            self._session,
            task.id,
            "PULL_REQUEST_COMMIT_MESSAGE_UPDATED",
            {"actor": actor, "old_revision": old_revision, "new_revision": new_revision},
        )
        await self._session.commit()
        return True

    async def _reject(self, task_id: Any, reason: str) -> None:
        await record_event(
            self._session,
            task_id,
            "GITHUB_COMMENT_ACTION_REJECTED",
            {"reason": reason},
        )
        await self._session.commit()
