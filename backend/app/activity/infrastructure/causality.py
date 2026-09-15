"""Resolve explicit source identifiers in batches; chronology alone is never a causal link."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.domain.events import Activity, identifier, reference
from app.coordinator.infrastructure.models import CoordinatorAction, CoordinatorRun, HumanRequest
from app.engineering.infrastructure.task_models import TaskEvent


async def attach_references(session: AsyncSession, activities: list[Activity]) -> list[Activity]:
    action_ids = {identifier(a.payload.get("action_id")) for a in activities} - {None}
    request_ids = {
        identifier(a.payload.get("request_id") or a.payload.get("human_request_id"))
        for a in activities
    } - {None}
    actions: dict[UUID, UUID] = {}
    requests: dict[UUID, UUID] = {}
    if action_ids:
        actions = {
            id: run
            for id, run in await session.execute(
                select(CoordinatorAction.id, CoordinatorAction.run_id).where(
                    CoordinatorAction.id.in_(action_ids)
                )
            )
        }
    if request_ids:
        requests = {
            id: run
            for id, run in await session.execute(
                select(HumanRequest.id, HumanRequest.run_id).where(HumanRequest.id.in_(request_ids))
            )
        }
    run_ids = (
        (
            {
                identifier(a.payload.get("run_id"))
                for a in activities
                if a.kind.startswith("COORDINATOR_") or a.kind == "HUMAN_REQUIRED"
            }
            - {None}
        )
        | set(actions.values())
        | set(requests.values())
    )
    parents: dict[tuple[UUID | None, str], int] = {}
    triggers: dict[UUID, str | None] = {}
    if run_ids:
        triggers = {
            id: trigger
            for id, trigger in await session.execute(
                select(CoordinatorRun.id, CoordinatorRun.evidence["event_id"].as_string()).where(
                    CoordinatorRun.id.in_(run_ids)
                )
            )
        }
        rows = await session.execute(
            select(TaskEvent.id, TaskEvent.event_type, TaskEvent.payload["run_id"].as_string())
            .where(
                TaskEvent.event_type.in_(
                    ["COORDINATOR_STARTED", "COORDINATOR_DECIDED", "HUMAN_INPUT_REQUIRED"]
                ),
                TaskEvent.payload["run_id"].as_string().in_([str(i) for i in run_ids]),
            )
            .order_by(TaskEvent.id)
        )
        for event_id, kind, run_id in rows:
            parents[(identifier(run_id), kind)] = event_id
    result = []
    queued_jobs = {
        str(activity.payload["job_id"])
        for activity in activities
        if activity.kind == "JOB_STARTED" and activity.payload.get("job_id")
    }
    queued = (
        {
            job: id
            for id, job in await session.execute(
                select(TaskEvent.id, TaskEvent.payload["job_id"].as_string()).where(
                    TaskEvent.event_type == "JOB_QUEUED",
                    TaskEvent.payload["job_id"].as_string().in_(queued_jobs),
                )
            )
        }
        if queued_jobs
        else {}
    )
    for activity in activities:
        facts = activity.payload
        links = list(activity.references)
        if facts.get("parent_event_id"):
            links.append(reference("task_event", facts["parent_event_id"], "triggered_by"))
        for review in facts.get("review_cycle_ids", []):
            links.append(reference("review", review, "feedback_from"))
        if activity.kind == "JOB_STARTED" and (queue := queued.get(str(facts.get("job_id")))):
            links.append(reference("task_event", queue, "dequeued_from"))
        job = identifier(facts.get("job_id"))
        if job and activity.kind not in {"JOB_QUEUED", "JOB_STARTED", "JOB_FINISHED"}:
            links.append(reference("job", f"{job}:started", "executed_by"))
        if activity.kind == "AI_RUN_COMPLETED":
            links.append(reference("ai_run", f"{facts['run_id']}:started", "completes"))
        if activity.kind == "WORK_PLAN_UPDATED" and facts.get("run_id"):
            links.append(reference("ai_run", f"{facts['run_id']}:started", "planned_by"))
        if activity.kind == "ENGINEERING_COST_RECONCILED" and identifier(facts.get("run_id")):
            links.append(reference("ai_run", f"{facts['run_id']}:finished", "corrects_cost"))
        if facts.get("reply_to_id"):
            links.append(reference("message", facts["reply_to_id"], "reply_to"))
        if identifier(facts.get("review_cycle_id")):
            links.append(reference("review", facts["review_cycle_id"], "review_received"))
        if facts.get("message_id") and activity.source_type == "coordination_event":
            links.append(reference("message", facts["message_id"], "message_received"))
        action = identifier(facts.get("action_id"))
        request = identifier(facts.get("request_id") or facts.get("human_request_id"))
        run = (actions.get(action) if action else None) or (
            requests.get(request) if request else None
        )
        parent_kind = (
            "HUMAN_INPUT_REQUIRED"
            if identifier(facts.get("request_id") or facts.get("human_request_id")) in requests
            else "COORDINATOR_DECIDED"
        )
        if activity.kind.startswith("COORDINATOR_") or activity.kind == "HUMAN_REQUIRED":
            run = identifier(facts.get("run_id"))
            parent_kind = (
                "COORDINATOR_STARTED"
                if activity.kind == "COORDINATOR_DECIDED"
                else "COORDINATOR_DECIDED"
            )
        if activity.kind == "COORDINATOR_STARTED":
            if run and identifier(triggers.get(run)):
                links.append(reference("coordination_event", triggers[run], "triggered_by"))
        elif (parent := parents.get((run, parent_kind))) and not (
            activity.source_type == "task_event" and activity.source_id == str(parent)
        ):
            links.append(
                reference(
                    "task_event",
                    parent,
                    "responds_to" if parent_kind == "HUMAN_INPUT_REQUIRED" else "triggered_by",
                )
            )
        result.append(replace(activity, references=links))
    return result
