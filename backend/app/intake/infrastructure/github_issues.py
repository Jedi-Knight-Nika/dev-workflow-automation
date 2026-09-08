"""Explicit GitHub issue routing; untrusted issue text cannot enable paid execution."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.job_queue import request_execution
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.intake.infrastructure.engineering_events import requirements_changed
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
from app.platform.configuration.settings import get_settings
from app.repositories.infrastructure.models import Repository


async def issue_event(
    session: AsyncSession, repository: Repository, payload: dict[str, Any]
) -> None:
    issue = payload.get("issue") or {}
    if not isinstance(issue, dict) or issue.get("pull_request") or not issue.get("id"):
        return
    route = get_settings().github_issue_routes.get(f"{repository.owner}/{repository.name}")
    actor = str((payload.get("sender") or {}).get("id") or "")
    if not route or actor not in route.get("actor_ids", "").split(","):
        return
    action = payload.get("action")
    snapshot = await session.scalar(
        select(ExternalTaskSnapshot)
        .where(
            ExternalTaskSnapshot.provider == "github",
            ExternalTaskSnapshot.external_id == str(issue["id"]),
        )
        .with_for_update()
    )
    task = await session.get(Task, snapshot.task_id, with_for_update=True) if snapshot else None
    title, body = str(issue.get("title") or "").strip()[:500], str(issue.get("body") or "")
    if not title:
        return
    if task:
        if task.repository_id != repository.id or str(task.team_id) != route.get("team_id"):
            return
        if action == "closed" and task.status not in {"MERGED", "CANCELLED", "FAILED"}:
            await control_task(session, task, Action.CANCEL, actor=f"github:{actor}")
        elif action == "edited" and (title, body) != (task.title, task.description):
            await requirements_changed(session, task, title, body, source=f"github:{actor}")
            task.title, task.description = title, body
        return
    labels = {str(item.get("name")) for item in issue.get("labels", []) if isinstance(item, dict)}
    trigger = route.get("trigger_label")
    if (
        action not in {"opened", "labeled", "assigned"}
        or not trigger
        or trigger not in labels
        or issue.get("state") != "open"
    ):
        return
    task = Task(
        title=title,
        description=body,
        team_id=UUID(route["team_id"]),
        repository_id=repository.id,
        external_key=f"GITHUB-{issue['id']}",
    )
    session.add(task)
    await session.flush()
    session.add(
        ExternalTaskSnapshot(
            task_id=task.id,
            provider="github",
            external_id=str(issue["id"]),
            identifier=f"{repository.owner}/{repository.name}#{issue['number']}"[:100],
            raw_payload={
                "number": issue["number"],
                "repository_id": str(repository.id),
                "url": issue.get("html_url"),
                "labels": [{"name": label} for label in labels],
            },
        )
    )
    session.add(
        TaskEvent(
            task_id=task.id,
            source="github",
            event_type="TASK_CREATED",
            payload={"actor": f"github:{actor}", "issue_number": issue["number"]},
        )
    )
    await request_execution(session, task, actor=f"github:{actor}")
