from pathlib import Path

import httpx
import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    IndexStatus,
    Integration,
    Repository,
    Task,
    TaskState,
    ValidationRecord,
)
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth
from app.services.crypto import cipher
from app.services.github_events import evaluate_current_revision, focused_validation_payload
from app.services.linear_sync import sync_merged_task_to_linear
from app.services.orchestrator import record_event
from app.services.workspaces import run_git

log = structlog.get_logger()
TERMINAL_STATES = {TaskState.CANCELLED, TaskState.FAILED, TaskState.MERGED}


def _focused_reconciled_payload(item: dict[str, object]) -> dict[str, object]:
    kind = item["kind"]
    payload = item["payload"]
    if not isinstance(payload, dict):
        return {"reconciled": True}
    if kind == "CHECK":
        return {"reconciled": True, **focused_validation_payload("check_run", payload)}
    if kind == "STATUS":
        status = payload.get("status")
        return {
            "reconciled": True,
            **focused_validation_payload("status", status if isinstance(status, dict) else {}),
        }
    event_type = "pull_request_review" if kind == "REVIEW" else "pull_request_review_comment"
    return {"reconciled": True, **focused_validation_payload(event_type, payload)}


async def reconcile_startup(session: AsyncSession) -> int:
    """Reconcile durable tasks with local Git and authoritative GitHub PR state."""
    tasks = list(
        (await session.scalars(select(Task).where(Task.state.not_in(TERMINAL_STATES)))).all()
    )
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    client: GitHubClient | None = None
    if integration and integration.encrypted_credentials:
        try:
            auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
            client = GitHubClient(auth.token, auth.installation)
        except (InvalidToken, ValueError, TypeError) as exc:
            log.warning("startup_github_auth_unavailable", reason=str(exc))

    reconciled = 0
    for task in tasks:
        if task.workspace_path and Path(task.workspace_path).is_dir():
            try:
                local_head = await run_git("rev-parse", "HEAD", cwd=Path(task.workspace_path))
                if not task.pull_request_number and local_head != task.current_revision:
                    task.current_revision = local_head
                    await record_event(
                        session, task.id, "WORKSPACE_REVISION_RECONCILED", {"head_sha": local_head}
                    )
            except RuntimeError as exc:
                await record_event(
                    session,
                    task.id,
                    "WORKSPACE_RECONCILIATION_FAILED",
                    {"error": str(exc)[:1000]},
                )

        if client is None or task.pull_request_number is None or task.repository_id is None:
            continue
        repository = await session.get(Repository, task.repository_id)
        if repository is None:
            continue
        try:
            pull_request = await client.get_pull_request(
                repository.owner, repository.name, task.pull_request_number
            )
        except httpx.HTTPError as exc:
            log.warning(
                "startup_pull_request_refresh_failed",
                task_id=str(task.id),
                reason=str(exc),
            )
            continue
        if pull_request.merged:
            task.state = TaskState.MERGED
            task.current_revision = pull_request.merge_commit_sha or pull_request.head_sha
            repository.index_status = IndexStatus.QUEUED
            repository.index_error = None
            await record_event(
                session,
                task.id,
                "PULL_REQUEST_MERGE_RECONCILED",
                {"number": pull_request.number, "revision": task.current_revision},
                source="github",
            )
            await session.commit()
            await sync_merged_task_to_linear(session, task)
        elif pull_request.state.lower() == "closed":
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session,
                task.id,
                "PULL_REQUEST_CLOSE_RECONCILED",
                {"number": pull_request.number},
                source="github",
            )
        elif pull_request.head_sha != task.current_revision:
            task.current_revision = pull_request.head_sha
            task.state = TaskState.WAITING_GITHUB
            await record_event(
                session,
                task.id,
                "PULL_REQUEST_REVISION_RECONCILED",
                {"number": pull_request.number, "head_sha": pull_request.head_sha},
                source="github",
            )
        if pull_request.state.lower() == "open":
            evidence = await client.list_revision_evidence(
                repository.owner,
                repository.name,
                pull_request.number,
                pull_request.head_sha,
            )
            added = 0
            for item in evidence:
                existing = await session.scalar(
                    select(ValidationRecord.id).where(
                        ValidationRecord.task_id == task.id,
                        ValidationRecord.kind == item["kind"],
                        ValidationRecord.name == item["name"],
                        ValidationRecord.status == item["status"],
                        ValidationRecord.revision == item["revision"],
                        ValidationRecord.details_url == item["details_url"],
                    )
                )
                if existing is not None:
                    continue
                session.add(
                    ValidationRecord(
                        task_id=task.id,
                        kind=str(item["kind"]),
                        name=str(item["name"]),
                        status=str(item["status"]),
                        revision=str(item["revision"]),
                        details_url=(str(item["details_url"]) if item.get("details_url") else None),
                        payload=_focused_reconciled_payload(item),
                    )
                )
                added += 1
            if added:
                await record_event(
                    session,
                    task.id,
                    "GITHUB_EVIDENCE_RECONCILED",
                    {"revision": pull_request.head_sha, "records_added": added},
                    source="github",
                )
                await session.flush()
                await evaluate_current_revision(session, task)
        reconciled += 1
        await session.commit()
    return reconciled
