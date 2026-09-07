from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.pull_requests import MergeConflict, MergeTask, MergeUnavailable
from app.config import get_settings
from app.db.models import (
    IndexStatus,
    Integration,
    Job,
    JobRole,
    JobState,
    Repository,
    Task,
    TaskEvent,
    TaskMessage,
    TaskRepositoryScope,
    TaskState,
    ValidationRecord,
    WebhookDelivery,
)
from app.domain.webhooks import DeliveryRetryPolicy
from app.infrastructure.external_task_sync import sync_external_task_state
from app.infrastructure.persistence.job_operations import enqueue_job, record_event
from app.infrastructure.pull_requests.merge_workflow import SqlAlchemyGitHubMergeWorkflow
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth

SUCCESSFUL_CHECKS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
FAILED_CHECKS = {
    "FAILURE",
    "FAILED",
    "ERROR",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STALE",
}
BLOCKING_REVIEWS = {"CHANGES_REQUESTED"}
ACTIVE_JOB_STATES = {JobState.QUEUED, JobState.CLAIMED, JobState.RUNNING, JobState.RETRY_WAIT}
AUTHORIZED_MERGE_PERMISSIONS = {"admin", "maintain", "write"}
MERGE_APPROVAL_COMMENTS = {
    "/merge",
    "approve and merge",
    "approved",
    "looks good to me",
    "lgtm",
    "merge",
    "merge it",
    "go merge",
    "go ahead and merge",
    "please merge",
    "please merge it",
    "lgtm, merge it",
    "ready to merge",
}
MAX_DIAGNOSTIC_CHARS = 12_000
MAX_ANNOTATIONS = 20


def _bounded_text(value: Any, remaining: int) -> str:
    if not isinstance(value, str) or remaining <= 0:
        return ""
    normalized = "\n".join(line.rstrip() for line in value.splitlines()).strip()
    if len(normalized) <= remaining:
        return normalized
    return normalized[: max(0, remaining - 14)].rstrip() + "\n[TRUNCATED]"


def extract_ci_diagnostics(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Extract bounded, relevant CI failure context from an untrusted webhook payload."""
    diagnostics: dict[str, Any] = {"event_type": event_type}
    pieces: list[str] = []
    if event_type == "check_run":
        check = payload.get("check_run") or {}
        output = check.get("output") or {}
        diagnostics.update(
            {
                "name": check.get("name"),
                "conclusion": check.get("conclusion"),
                "details_url": check.get("details_url") or check.get("html_url"),
            }
        )
        for label, value in (
            ("title", output.get("title")),
            ("summary", output.get("summary")),
            ("text", output.get("text")),
        ):
            text = _bounded_text(value, MAX_DIAGNOSTIC_CHARS - sum(map(len, pieces)))
            if text:
                pieces.append(f"{label}: {text}")
        annotations = output.get("annotations")
        if isinstance(annotations, list):
            diagnostics["annotations"] = [
                {
                    "path": item.get("path"),
                    "start_line": item.get("start_line"),
                    "end_line": item.get("end_line"),
                    "level": item.get("annotation_level"),
                    "message": _bounded_text(item.get("message"), 1_000),
                }
                for item in annotations[:MAX_ANNOTATIONS]
                if isinstance(item, dict)
            ]
    elif event_type == "status":
        diagnostics.update(
            {
                "name": payload.get("context"),
                "conclusion": payload.get("state"),
                "details_url": payload.get("target_url"),
            }
        )
        description = _bounded_text(payload.get("description"), MAX_DIAGNOSTIC_CHARS)
        if description:
            pieces.append(f"description: {description}")
    elif event_type == "check_suite":
        suite = payload.get("check_suite") or {}
        diagnostics.update(
            {
                "name": (suite.get("app") or {}).get("name"),
                "conclusion": suite.get("conclusion"),
                "details_url": suite.get("url"),
            }
        )
    diagnostics["excerpt"] = _bounded_text("\n\n".join(pieces), MAX_DIAGNOSTIC_CHARS)
    return diagnostics


def focused_validation_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_type in {"check_run", "check_suite", "status"}:
        return {"ci_diagnostics": extract_ci_diagnostics(event_type, payload)}
    if event_type == "pull_request_review_comment":
        comment = payload.get("comment") or {}
        return {
            "review_comment": {
                "body": _bounded_text(comment.get("body"), MAX_DIAGNOSTIC_CHARS),
                "path": comment.get("path"),
                "line": comment.get("line") or comment.get("original_line"),
                "url": comment.get("html_url"),
            }
        }
    if event_type == "pull_request_review":
        review = payload.get("review") or {}
        return {
            "review": {
                "body": _bounded_text(review.get("body"), MAX_DIAGNOSTIC_CHARS),
                "state": review.get("state"),
                "url": review.get("html_url"),
            }
        }
    return {}


def conversational_comment(event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    action = payload.get("action")
    if action not in {"created", "edited", "submitted"}:
        return None
    if event_type == "issue_comment" and payload.get("issue", {}).get("pull_request"):
        comment = payload.get("comment") or {}
    elif event_type == "pull_request_review":
        review = payload.get("review") or {}
        if str(review.get("state", "")).upper() != "COMMENTED":
            return None
        comment = review
    else:
        return None
    body = str(comment.get("body") or "").strip()
    if not body:
        return None
    return {
        "source": "github",
        "event_type": event_type,
        "author": (comment.get("user") or {}).get("login"),
        "url": comment.get("html_url"),
        "raw_text": body,
    }


def merge_approval_actor(event_type: str, payload: dict[str, Any]) -> str | None:
    """Return the actor for an explicit PR merge approval, never inferred prose."""
    if event_type == "pull_request_review" and payload.get("action") == "submitted":
        review = payload.get("review") or {}
        if str(review.get("state") or "").upper() == "APPROVED":
            return str((review.get("user") or {}).get("login") or "").strip() or None
        return None
    if (
        event_type == "issue_comment"
        and payload.get("action") == "created"
        and "pull_request" in (payload.get("issue") or {})
    ):
        comment = payload.get("comment") or {}
        body = " ".join(str(comment.get("body") or "").lower().split()).rstrip(".! ")
        if body in MERGE_APPROVAL_COMMENTS:
            return str((comment.get("user") or {}).get("login") or "").strip() or None
    return None


def pull_request_number(payload: dict[str, Any]) -> int | None:
    value = (
        (payload.get("pull_request") or {}).get("number")
        or payload.get("number")
        or (payload.get("issue") or {}).get("number")
    )
    return value if isinstance(value, int) else None


async def _authorized_merge_approval(
    session: AsyncSession, repository: Repository, actor: str
) -> bool:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    if integration is None or integration.encrypted_credentials is None:
        return False
    try:
        auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
        permission = await GitHubClient(auth.token, auth.installation).collaborator_permission(
            repository.owner, repository.name, actor
        )
    except (httpx.HTTPError, RuntimeError, TypeError, ValueError):
        return False
    return permission in AUTHORIZED_MERGE_PERMISSIONS


async def _request_merge_from_github(
    session: AsyncSession,
    task: Task,
    repository: Repository,
    actor: str,
    scope: TaskRepositoryScope | None = None,
    reviewed_revision: str | None = None,
) -> None:
    revision = scope.current_revision if scope else task.current_revision
    if reviewed_revision and reviewed_revision != revision:
        await record_event(
            session,
            task.id,
            "PULL_REQUEST_MERGE_APPROVAL_REJECTED",
            {"actor": actor, "reason": "Approval belongs to an older PR revision"},
            source="github",
        )
        return
    if not await _authorized_merge_approval(session, repository, actor):
        await record_event(
            session,
            task.id,
            "PULL_REQUEST_MERGE_APPROVAL_REJECTED",
            {"actor": actor, "reason": "GitHub collaborator lacks write permission"},
            source="github",
        )
        return
    await record_event(
        session,
        task.id,
        "PULL_REQUEST_MERGE_REQUESTED",
        {
            "actor": actor,
            "source": "github",
            "trigger": "approval",
            "revision": revision,
            "repository_id": str(repository.id),
        },
        source="github",
    )
    await session.flush()
    try:
        await MergeTask(SqlAlchemyGitHubMergeWorkflow(session, repository.id)).execute(task.id)
    except (MergeConflict, MergeUnavailable, ValueError) as exc:
        await record_event(
            session,
            task.id,
            "PULL_REQUEST_AUTO_MERGE_DEFERRED",
            {"actor": actor, "reason": str(exc)},
            source="github",
        )


def validation_from_event(
    event_type: str, payload: dict[str, Any]
) -> tuple[str, str, str, str, str | None] | None:
    if event_type == "check_run":
        item = payload.get("check_run", {})
        status = item.get("conclusion") or item.get("status") or "pending"
        return (
            "CHECK",
            item.get("name", "check"),
            str(status).upper(),
            item.get("head_sha", ""),
            item.get("html_url"),
        )
    if event_type == "check_suite":
        item = payload.get("check_suite", {})
        status = item.get("conclusion") or item.get("status") or "pending"
        return (
            "CHECK_SUITE",
            item.get("app", {}).get("name", "check suite"),
            str(status).upper(),
            item.get("head_sha", ""),
            item.get("url"),
        )
    if event_type == "status":
        return (
            "STATUS",
            payload.get("context", "status"),
            str(payload.get("state", "pending")).upper(),
            payload.get("sha", ""),
            payload.get("target_url"),
        )
    if event_type == "pull_request_review" and payload.get("action") == "submitted":
        review = payload.get("review", {})
        revision = review.get("commit_id") or payload.get("pull_request", {}).get("head", {}).get(
            "sha", ""
        )
        return (
            "REVIEW",
            review.get("user", {}).get("login", "review"),
            str(review.get("state", "commented")).upper(),
            revision,
            review.get("html_url"),
        )
    if event_type == "pull_request_review_comment" and payload.get("action") in {
        "created",
        "edited",
    }:
        comment = payload.get("comment", {})
        return (
            "REVIEW_COMMENT",
            comment.get("user", {}).get("login", "review comment"),
            "ACTION_REQUIRED",
            comment.get("commit_id")
            or payload.get("pull_request", {}).get("head", {}).get("sha", ""),
            comment.get("html_url"),
        )
    return None


async def evaluate_current_revision(
    session: AsyncSession, task: Task, scope: TaskRepositoryScope | None = None
) -> None:
    current_revision = scope.current_revision if scope else task.current_revision
    repository_id = scope.repository_id if scope else task.repository_id
    if not current_revision or task.state == TaskState.MERGED or scope and scope.merged_at:
        return
    records = list(
        (
            await session.scalars(
                select(ValidationRecord)
                .where(
                    ValidationRecord.task_id == task.id,
                    ValidationRecord.revision == current_revision,
                )
                .order_by(ValidationRecord.created_at.desc())
            )
        ).all()
    )
    latest: dict[tuple[str, str], ValidationRecord] = {}
    for record in records:
        if record.payload.get("repository_id") != str(repository_id) and not (
            record.payload.get("repository_id") is None and repository_id == task.repository_id
        ):
            continue
        latest.setdefault((record.kind, record.name), record)
    checks = [
        record for record in latest.values() if record.kind in {"CHECK", "CHECK_SUITE", "STATUS"}
    ]
    reviews = [record for record in latest.values() if record.kind == "REVIEW"]
    review_comments = [record for record in latest.values() if record.kind == "REVIEW_COMMENT"]
    incomplete = [record for record in checks if record.status not in SUCCESSFUL_CHECKS]
    failing = [record for record in checks if record.status in FAILED_CHECKS]
    blocking_reviews = [record for record in reviews if record.status in BLOCKING_REVIEWS]
    if not incomplete and not blocking_reviews and checks:
        task.state = TaskState.READY_TO_MERGE
        await record_event(
            session,
            task.id,
            "TASK_READY_TO_MERGE",
            {"revision": current_revision, "repository_id": str(repository_id)},
        )
        merge_request = await session.scalar(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task.id,
                TaskEvent.event_type == "PULL_REQUEST_MERGE_REQUESTED",
                TaskEvent.payload["revision"].as_string() == current_revision,
                TaskEvent.payload["repository_id"].as_string() == str(repository_id),
            )
            .order_by(TaskEvent.created_at.desc())
            .limit(1)
        )
        if (
            merge_request is not None
            and merge_request.payload.get("revision") == current_revision
            and merge_request.payload.get("repository_id") == str(repository_id)
        ):
            try:
                await MergeTask(SqlAlchemyGitHubMergeWorkflow(session, repository_id)).execute(
                    task.id
                )
            except (MergeConflict, MergeUnavailable, ValueError) as exc:
                await record_event(
                    session,
                    task.id,
                    "PULL_REQUEST_AUTO_MERGE_DEFERRED",
                    {"reason": str(exc)},
                )
        return
    blocking = failing + blocking_reviews + review_comments
    if not blocking:
        return
    active = await session.scalar(
        select(func.count(Job.id)).where(
            Job.task_id == task.id,
            Job.role == JobRole.EXECUTOR,
            Job.state.in_(ACTIVE_JOB_STATES),
        )
    )
    if active:
        return
    first = blocking[0]
    review_repair = first.kind in {"REVIEW", "REVIEW_COMMENT"}
    action = "REPAIR_GITHUB_REVIEW" if review_repair else "REPAIR_CI"
    category_limit = (
        get_settings().max_external_review_repairs_per_task
        if review_repair
        else get_settings().max_ci_repairs_per_task
    )
    category_total = await session.scalar(
        select(func.count(Job.id)).where(
            Job.task_id == task.id,
            Job.role == JobRole.EXECUTOR,
            Job.action == action,
        )
    )
    total = await session.scalar(
        select(func.count(Job.id)).where(Job.task_id == task.id, Job.role == JobRole.EXECUTOR)
    )
    if (total or 0) >= get_settings().max_executor_jobs_per_task or (
        category_total or 0
    ) >= category_limit:
        task.state = TaskState.NEEDS_HUMAN
        await record_event(
            session,
            task.id,
            "REPAIR_LIMIT_REACHED",
            {"action": action, "category_limit": category_limit},
        )
        return
    await enqueue_job(
        session,
        task,
        JobRole.EXECUTOR,
        action,
        payload={
            "kind": first.kind,
            "name": first.name,
            "status": first.status,
            "revision": first.revision,
            "details_url": first.details_url,
            "payload": first.payload,
        },
    )
    await record_event(
        session,
        task.id,
        "EXTERNAL_REPAIR_QUEUED",
        {"action": action, "revision": first.revision, "name": first.name},
    )


async def process_github_event(
    session: AsyncSession, event_type: str, payload: dict[str, Any]
) -> None:
    repository_payload = payload.get("repository") or {}
    external_id = repository_payload.get("id")
    if external_id is None:
        return
    repository = await session.scalar(
        select(Repository).where(
            Repository.provider == "github", Repository.external_repo_id == str(external_id)
        )
    )
    if repository is None:
        return
    pull_request = payload.get("pull_request") or {}
    number = pull_request_number(payload)
    if number is None and event_type in {"check_run", "check_suite"}:
        pull_requests = payload.get(event_type, {}).get("pull_requests", [])
        if pull_requests:
            number = pull_requests[0].get("number")
    evidence = validation_from_event(event_type, payload)
    scope = None
    if number is not None:
        scope = await session.scalar(
            select(TaskRepositoryScope).where(
                TaskRepositoryScope.repository_id == repository.id,
                TaskRepositoryScope.pull_request_number == int(number),
            )
        )
    elif evidence and evidence[3]:
        scope = await session.scalar(
            select(TaskRepositoryScope).where(
                TaskRepositoryScope.repository_id == repository.id,
                TaskRepositoryScope.current_revision == evidence[3],
            )
        )
    if number is not None:
        task = await session.scalar(
            select(Task).where(
                Task.repository_id == repository.id, Task.pull_request_number == int(number)
            )
        )
    elif evidence and evidence[3]:
        task = await session.scalar(
            select(Task).where(
                Task.repository_id == repository.id, Task.current_revision == evidence[3]
            )
        )
    else:
        return
    if task is None and scope is not None:
        task = await session.get(Task, scope.task_id)
    if task is None:
        return
    approval_actor = merge_approval_actor(event_type, payload)
    if approval_actor:
        await _request_merge_from_github(
            session,
            task,
            repository,
            approval_actor,
            scope,
            (payload.get("review") or {}).get("commit_id"),
        )
    comment = conversational_comment(event_type, payload)
    if comment and not approval_actor:
        comment["repository_id"] = str(repository.id)
        comment["pull_request_number"] = number
        comment["previous_state"] = task.state.value
        active_intake = await session.scalar(
            select(func.count(Job.id)).where(
                Job.task_id == task.id,
                Job.role == JobRole.DELIVERER,
                Job.state.in_(ACTIVE_JOB_STATES),
            )
        )
        if not active_intake:
            intake_job = await enqueue_job(
                session,
                task,
                JobRole.DELIVERER,
                "INTERPRET_EXTERNAL_COMMENT",
                payload=comment,
            )
            session.add(
                TaskMessage(
                    task_id=task.id,
                    job_id=intake_job.id,
                    author_type="EXTERNAL",
                    author_name=str(comment.get("author") or "GitHub user")[:120],
                    kind="COMMENT",
                    body=str(comment["raw_text"])[:8_000],
                    context={
                        "source": "github",
                        "url": comment.get("url"),
                        "task_state": task.state.value,
                    },
                )
            )
            await record_event(
                session,
                task.id,
                "EXTERNAL_COMMENT_QUEUED_FOR_INTAKE",
                {key: value for key, value in comment.items() if key != "raw_text"},
                source="github",
            )
    if event_type == "pull_request" and payload.get("action") in {
        "opened",
        "reopened",
        "synchronize",
    }:
        revision = pull_request.get("head", {}).get("sha")
        if revision:
            if scope:
                scope.current_revision = revision
                scope.merged_at = None
                scope.merge_commit_sha = None
            if scope is None or scope.is_primary:
                task.current_revision = revision
            task.state = TaskState.WAITING_GITHUB
            await record_event(
                session, task.id, "PULL_REQUEST_SYNCHRONIZED", {"head_sha": revision}
            )
    if event_type == "pull_request" and payload.get("action") == "closed":
        if pull_request.get("merged"):
            merged_sha = (
                pull_request.get("merge_commit_sha")
                or pull_request.get("head", {}).get("sha")
                or task.current_revision
            )
            if scope:
                scope.merged_at = datetime.now(UTC)
                scope.merge_commit_sha = merged_sha
                await session.flush()
            pending_scope = await session.scalar(
                select(TaskRepositoryScope.id)
                .where(
                    TaskRepositoryScope.task_id == task.id,
                    TaskRepositoryScope.changed.is_(True),
                    TaskRepositoryScope.merged_at.is_(None),
                )
                .limit(1)
            )
            task.state = TaskState.WAITING_GITHUB if pending_scope else TaskState.MERGED
            if pending_scope is None:
                task.completed_at = datetime.now(UTC)
            if scope is None or scope.is_primary:
                task.current_revision = merged_sha
            repository.index_status = IndexStatus.QUEUED
            repository.index_error = None
            await record_event(
                session,
                task.id,
                "PULL_REQUEST_MERGED_EXTERNALLY",
                {
                    "number": number,
                    "merge_commit_sha": pull_request.get("merge_commit_sha"),
                },
                source="github",
            )
            await session.flush()
            await sync_external_task_state(session, task)
        else:
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session,
                task.id,
                "PULL_REQUEST_CLOSED_EXTERNALLY",
                {"number": number},
                source="github",
            )
    if evidence:
        kind, name, validation_status, revision, details_url = evidence
        if revision:
            validation_payload = focused_validation_payload(event_type, payload)
            check_run = payload.get("check_run") or {}
            if (
                event_type == "check_run"
                and validation_status in FAILED_CHECKS
                and isinstance(check_run.get("id"), int)
            ):
                integration = await session.scalar(
                    select(Integration).where(Integration.provider_name == "github")
                )
                if integration and integration.encrypted_credentials:
                    try:
                        auth = await resolve_github_auth(
                            cipher.decrypt(integration.encrypted_credentials)
                        )
                        fetched = await GitHubClient(
                            auth.token, auth.installation
                        ).get_check_run_diagnostics(
                            repository.owner, repository.name, check_run["id"]
                        )
                        fetched_check = fetched["check_run"]
                        output = dict(fetched_check.get("output") or {})
                        output["annotations"] = fetched["annotations"]
                        if fetched["actions_log"]:
                            output["text"] = "\n\n".join(
                                value
                                for value in (output.get("text"), fetched["actions_log"])
                                if value
                            )
                        validation_payload = focused_validation_payload(
                            event_type, {"check_run": {**fetched_check, "output": output}}
                        )
                    except (httpx.HTTPError, RuntimeError, TypeError, ValueError):
                        pass
            session.add(
                ValidationRecord(
                    task_id=task.id,
                    kind=kind,
                    name=name,
                    status=validation_status,
                    revision=revision,
                    details_url=details_url,
                    payload={**validation_payload, "repository_id": str(repository.id)},
                )
            )
            await record_event(
                session,
                task.id,
                "VALIDATION_RECORDED",
                {
                    "kind": kind,
                    "name": name,
                    "status": validation_status,
                    "revision": revision,
                },
            )
            await session.flush()
            await evaluate_current_revision(session, task, scope)


async def process_next_github_delivery(session: AsyncSession, max_attempts: int = 5) -> bool:
    retry_policy = DeliveryRetryPolicy(max_attempts)
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(WebhookDelivery.provider == "github", WebhookDelivery.status == "RECEIVED")
        .order_by(WebhookDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return False
    delivery_id = delivery.id
    try:
        delivery.attempts += 1
        await process_github_event(session, delivery.event_type, delivery.payload)
        delivery.status = "PROCESSED"
        delivery.last_error = None
        delivery.processed_at = datetime.now(UTC)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed = await session.get(WebhookDelivery, delivery_id, with_for_update=True)
        if failed is None:
            raise
        failed.attempts += 1
        failed.last_error = retry_policy.error_message(exc)
        if retry_policy.exhausted(failed.attempts):
            failed.status = "FAILED"
            failed.processed_at = datetime.now(UTC)
        await session.commit()
    return True
