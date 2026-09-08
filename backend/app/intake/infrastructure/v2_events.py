"""Small, durable event routing. No repository context or workflow graph."""

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.models import DeveloperSession
from app.delivery.infrastructure.git_transport import github_token
from app.delivery.infrastructure.github import GitHubDelivery, github_client
from app.delivery.infrastructure.review_state import review_state
from app.delivery.infrastructure.workflow import delivery_gate
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.jobs import enqueue_phase
from app.engineering.infrastructure.lifecycle import record_transition
from app.engineering.infrastructure.models import ReviewCycle
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.intake.application.interpret import InterpretEvent
from app.intake.domain.events import Event, Intent, requirement_fingerprint
from app.intake.infrastructure.authorization import actor_allowed
from app.intake.infrastructure.observed_reviews import observe_review_messages
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.automation import read_policy


async def apply_pending_feedback(session: AsyncSession, task: Task) -> bool:
    if (
        task.status in {"PAUSED", "WAITING_HUMAN", "MERGED", "CANCELLED", "FAILED"}
        or task.manual_takeover
    ):
        return False
    if task.stage != "REVIEWING":
        return False
    rows = list(
        await session.scalars(
            select(ReviewCycle)
            .where(
                ReviewCycle.task_id == task.id,
                ReviewCycle.decision == "FEEDBACK_PENDING",
                ReviewCycle.head_sha == task.current_revision,
            )
            .order_by(ReviewCycle.created_at)
        )
    )
    authorized = []
    for row in rows:
        if await actor_allowed(
            session,
            task,
            str(row.feedback.get("provider") or "github"),
            row.actor or "",
            actor_type=row.feedback.get("actor_type"),
        ):
            authorized.append(row)
        else:
            row.decision = "AUTHORITY_REVOKED"
    rows = authorized
    if not rows:
        return False
    native = await session.scalar(
        select(DeveloperSession)
        .where(DeveloperSession.task_id == task.id)
        .order_by(DeveloperSession.generation.desc())
        .limit(1)
        .with_for_update()
    )
    if native is None or not native.native_session_id:
        raise ValueError("Feedback requires the task's persisted native session")
    delta = "\n\n".join(str(row.feedback.get("body") or "") for row in rows)
    if len(delta) > 16000:
        await record_transition(
            session,
            task.id,
            Action.BLOCK,
            expected_version=task.lifecycle_version,
            actor="review",
            wait_reason=WaitReason.MISSING_REQUIREMENT,
        )
        return True
    native.checkpoint = {
        **native.checkpoint,
        "next_feedback": "Address this new authorized PR feedback in the same session:\n" + delta,
    }
    for row in rows:
        row.decision = "FEEDBACK_APPLIED"
    await record_transition(
        session,
        task.id,
        Action.REVIEW_FIX,
        expected_version=task.lifecycle_version,
        actor="github-review",
    )
    await enqueue_phase(session, task)
    return True


async def github_event(
    session: AsyncSession, task: Task, repository: Repository, kind: str, payload: dict[str, Any]
) -> None:
    # Stable payload fingerprint dedups provider redelivery even under a new delivery UUID.
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    event_id = f"github:{kind}:{digest}"
    task = await session.get(Task, task.id, with_for_update=True, populate_existing=True) or task
    if await session.scalar(
        select(ReviewCycle.id).where(
            ReviewCycle.task_id == task.id, ReviewCycle.external_event_id == event_id
        )
    ):
        return
    if task.team_id is None or not task.pull_request_number or not task.current_revision:
        return
    policy = await read_policy(session, task.team_id)
    review = payload.get("review") or payload.get("comment") or {}
    actor = str((review.get("user") or payload.get("sender") or {}).get("id") or "")
    body = str(review.get("body") or "").strip()
    sha = (
        review.get("commit_id")
        or (payload.get("pull_request") or {}).get("head", {}).get("sha")
        or task.current_revision
    )
    cycle = ReviewCycle(
        task_id=task.id,
        external_event_id=event_id,
        head_sha=sha,
        actor=actor,
        decision="OBSERVED",
        feedback={},
    )
    session.add(cycle)
    await session.flush()
    if kind in {
        "issue_comment",
        "pull_request_review_comment",
        "pull_request_review",
    } and payload.get("action") in {"created", "edited", "submitted"}:
        if (
            not await actor_allowed(
                session,
                task,
                "github",
                actor,
                actor_type=(review.get("user") or payload.get("sender") or {}).get("type"),
            )
            or sha != task.current_revision
        ):
            cycle.decision = "UNAUTHORIZED_OR_STALE"
            return
        if len(body) > 16000:
            cycle.decision = "TOO_LARGE"
            return
        formal_changes = (
            kind == "pull_request_review" and review.get("state", "").upper() == "CHANGES_REQUESTED"
        )
        formal_approval = (
            kind == "pull_request_review" and review.get("state", "").upper() == "APPROVED"
        )
        command_approval = (
            not policy.require_formal_approval
            and kind == "issue_comment"
            and bool(re.fullmatch(r"/lgtm " + re.escape(task.current_revision), body))
        )
        if formal_changes and not body:
            async with github_client(await github_token(session)) as api:
                comments = await GitHubDelivery(api, repository.owner, repository.name).pages(
                    f"/pulls/{task.pull_request_number}/reviews/{review['id']}/comments"
                )
            body = "\n".join(
                f"{value.get('path', '')}:{value.get('line', '')}: {value.get('body', '')}"
                for value in comments
            )
        if formal_changes or (
            policy.require_formal_approval and not formal_approval and not command_approval and body
        ):
            # Ordinary prose is claimed separately, outside webhook/Task locks.
            if not formal_changes:
                cycle.decision, cycle.feedback = (
                    "CLASSIFY_PENDING",
                    {"body": body, "actor_type": (review.get("user") or {}).get("type")},
                )
                return
            interpretation = await InterpretEvent().execute(
                Event(
                    "github",
                    event_id,
                    "review_changes_requested" if formal_changes else "comment",
                    actor,
                    body,
                    str(task.id),
                    sha,
                    True,
                )
            )
            if interpretation.intent in {Intent.FEEDBACK, Intent.REQUIREMENT_CHANGE}:
                cycle.decision, cycle.feedback = (
                    "FEEDBACK_PENDING",
                    {"body": body, "actor_type": (review.get("user") or {}).get("type")},
                )
                await session.flush()
                await apply_pending_feedback(session, task)
                return
            if interpretation.intent == Intent.UNKNOWN:
                cycle.decision, cycle.feedback = "NEEDS_CLASSIFICATION", {"body": body}
                if task.status not in {"PAUSED", "WAITING_HUMAN", "MERGED", "CANCELLED", "FAILED"}:
                    await record_transition(
                        session,
                        task.id,
                        Action.BLOCK,
                        expected_version=task.lifecycle_version,
                        actor="interpreter",
                        wait_reason=WaitReason.MISSING_REQUIREMENT,
                    )
                return
    if task.stage != "REVIEWING" or task.status != "WAITING_EXTERNAL" or task.manual_takeover:
        return
    if await apply_pending_feedback(session, task):
        return
    merge_policy, checks, validated = await delivery_gate(session, task, repository)
    reviewed, validated_at = await review_state(session, task)
    async with github_client(await github_token(session)) as api:
        evidence, pull = await GitHubDelivery(api, repository.owner, repository.name).evidence(
            task.pull_request_number,
            task.current_revision,
            validated,
            merge_policy,
            checks,
            runnable=not task.archived_at,
            reviewed_messages=reviewed,
            validated_at=validated_at,
        )
    await observe_review_messages(session, task, evidence.review_messages)
    if pull["head"]["sha"] != task.current_revision:
        cycle.decision = "HEAD_CHANGED"
        await record_transition(
            session,
            task.id,
            Action.BLOCK,
            expected_version=task.lifecycle_version,
            actor="github",
            wait_reason=WaitReason.MERGE_CONFLICT,
        )
        return
    if pull.get("merged"):
        # Reconcile a fact already confirmed by GitHub (including a human merge),
        # not authority to submit a merge mutation. Paused work was excluded above.
        cycle.decision = "MERGED_EXTERNALLY"
        await record_transition(
            session,
            task.id,
            Action.MERGE_AUTHORIZED,
            expected_version=task.lifecycle_version,
            actor="github-merged-fact",
        )
        await record_transition(
            session,
            task.id,
            Action.MERGED,
            expected_version=task.lifecycle_version,
            actor="github-merged-fact",
        )
        return
    blockers = merge_policy.blockers(evidence)
    cycle.decision = "MERGE_ELIGIBLE" if not blockers else "WAITING"
    cycle.feedback = {"blockers": blockers}
    if not blockers:
        await record_transition(
            session,
            task.id,
            Action.MERGE_AUTHORIZED,
            expected_version=task.lifecycle_version,
            actor="github-evidence",
        )
        await enqueue_phase(session, task)


async def requirements_changed(
    session: AsyncSession, task: Task, title: str, description: str, *, source: str
) -> None:
    if requirement_fingerprint(task.title, task.description) == requirement_fingerprint(
        title, description
    ):
        return
    session.add(
        TaskEvent(
            task_id=task.id,
            source=source,
            event_type="V2_REQUIREMENT_CHANGED",
            payload={"fingerprint": requirement_fingerprint(title, description)},
        )
    )
    if task.status in {"MERGED", "CANCELLED", "FAILED"}:
        return
    # Material changes revoke in-flight work; resuming unknown-cost inference requires inspection.
    # Keep the exact delta in the native checkpoint rather than another accumulated plan.
    native = await session.scalar(
        select(DeveloperSession)
        .where(DeveloperSession.task_id == task.id)
        .order_by(DeveloperSession.generation.desc())
        .limit(1)
        .with_for_update()
    )
    if native:
        native.checkpoint = {
            **native.checkpoint,
            "next_feedback": f"Requirements changed. Current request:\n{title}\n\n{description}"[
                :24000
            ],
        }
    await control_task(session, task, Action.PAUSE, actor=source)
    await record_transition(
        session,
        task.id,
        Action.REVISE_REQUIREMENT,
        expected_version=task.lifecycle_version,
        actor=source,
    )
