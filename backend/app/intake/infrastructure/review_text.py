from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import AIRun
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.lifecycle import record_transition
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.models import ReviewCycle
from app.engineering.infrastructure.task_models import Task
from app.intake.application.interpret import InterpretEvent, TextInterpreter
from app.intake.domain.events import Event, Intent, classify
from app.intake.infrastructure.authorization import actor_allowed
from app.intake.infrastructure.metered import CloudInterpreter, MeteredLocalInterpreter
from app.intake.infrastructure.ollama import OllamaInterpreter
from app.intake.infrastructure.v2_events import apply_pending_feedback, github_event
from app.platform.configuration.settings import Settings
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.models import TeamAgentProfile

# Local + two cloud attempts can each take up to two minutes. Recovery must not
# race a healthy chain; the extra margin covers metering and provider admission.
CLAIM_TIMEOUT = timedelta(minutes=15)


async def process_review_text(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> bool:
    expired = datetime.now(UTC) - CLAIM_TIMEOUT
    async with sessions.begin() as session:
        cycle = await session.scalar(
            select(ReviewCycle)
            .where(
                or_(
                    ReviewCycle.decision == "CLASSIFY_PENDING",
                    and_(
                        ReviewCycle.decision == "CLASSIFYING",
                        ReviewCycle.feedback["claimed_at"].as_string() <= expired.isoformat(),
                    ),
                )
            )
            .order_by(ReviewCycle.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if cycle is None:
            return False
        task = await session.get(Task, cycle.task_id)
        if task is None or task.team_id is None:
            cycle.decision = "OBSOLETE"
            return True
        if cycle.decision == "CLASSIFYING":
            # Crash recovery never silently repeats an admitted paid request.
            # Cloud requests have a <=120s timeout. Only sufficiently old,
            # jobless interpreter runs can belong to this recovery path.
            lost = await session.scalars(
                select(AIRun)
                .where(
                    AIRun.task_id == task.id,
                    AIRun.role_kind == "INTERPRETER",
                    AIRun.job_id.is_(None),
                    AIRun.status == "RUNNING",
                    AIRun.started_at < datetime.now(UTC) - timedelta(minutes=5),
                )
                .with_for_update()
            )
            for run in lost:
                run.status, run.failure_code, run.finished_at = (
                    "INTERRUPTED",
                    "INTERPRETER_CLAIM_EXPIRED",
                    datetime.now(UTC),
                )
            cycle.decision = "NEEDS_CLASSIFICATION"
            session.add(
                TaskMessage(
                    task_id=task.id,
                    author_type="SYSTEM",
                    author_name="Interpreter",
                    kind="UPDATE",
                    body="Interpretation was interrupted. Inspect usage before explicitly classifying this feedback.",
                    context={"review_cycle_id": str(cycle.id)},
                )
            )
            return True
        if task.status in {"MERGED", "CANCELLED", "FAILED"}:
            cycle.decision = "OBSOLETE"
            return True
        cycle_id, task_id = cycle.id, task.id
        profile = await session.scalar(
            select(TeamAgentProfile).where(
                TeamAgentProfile.team_id == task.team_id,
                TeamAgentProfile.role_kind == "INTERPRETER",
            )
        )
        local_model = (
            profile.model
            if profile and profile.provider == "ollama"
            else settings.interpreter_model
        )
        models = list(settings.interpreter_cloud_models)
        if profile and profile.provider in {"openai", "deepseek"} and profile.hard_budget_usd:
            configured = f"{profile.provider}/{profile.model}"
            models = [configured, *(model for model in models if model != configured)][:2]
        role_budget = profile.hard_budget_usd if profile else None
        event = Event(
            str(cycle.feedback.get("provider") or "github"),
            cycle.external_event_id,
            "comment",
            cycle.actor or "",
            str(cycle.feedback.get("body") or ""),
            str(cycle.feedback.get("task_reference") or task.id),
            cycle.head_sha,
            True,
        )
        policy = await read_policy(session, task.team_id)
        if not await actor_allowed(
            session, task, event.provider, event.actor, actor_type=cycle.feedback.get("actor_type")
        ):
            cycle.decision = "AUTHORITY_REVOKED"
            return True
        deterministic = classify(event)
        is_control = deterministic is not None and deterministic.intent in {
            Intent.PAUSE,
            Intent.RESUME,
            Intent.CANCEL,
        }
        if (
            is_control
            and event.provider == "github"
            and event.actor not in policy.authorized_reviewer_ids
        ):
            cycle.decision = "AUTHORITY_REVOKED"
            return True
        if not is_control and (task.status in {"PAUSED", "WAITING_HUMAN"} or task.manual_takeover):
            cycle.decision = "CLASSIFY_AFTER_RESUME"
            return True
        if not is_control and task.stage != "REVIEWING":
            cycle.decision = "CLASSIFY_AFTER_PHASE"
            return True
        if not is_control and cycle.head_sha != (task.current_revision or ""):
            cycle.decision = "STALE"
            return True
        cycle.decision, cycle.feedback = (
            "CLASSIFYING",
            {**cycle.feedback, "claimed_at": datetime.now(UTC).isoformat()},
        )
    # There is deliberately no Task/Team lock held while a local/cloud model runs.
    chain: list[TextInterpreter] = []
    if settings.local_event_interpreter:
        chain.append(
            MeteredLocalInterpreter(
                sessions,
                task_id,
                OllamaInterpreter(
                    settings.ollama_base_url,
                    local_model,
                    settings.interpreter_timeout_seconds,
                ),
            )
        )
    chain.extend(
        CloudInterpreter(
            sessions,
            task_id,
            model,
            Decimal(str(settings.interpreter_cloud_request_limit_usd)),
            settings.interpreter_timeout_seconds,
            role_budget=role_budget,
        )
        for model in models
    )
    result = await InterpretEvent(
        tuple(chain), allow_approval=not policy.require_formal_approval
    ).execute(event)
    async with sessions.begin() as session:
        task = await session.get(Task, task_id, with_for_update=True)
        cycle = await session.get(ReviewCycle, cycle_id, with_for_update=True)
        if task is None or task.team_id is None or cycle is None or cycle.decision != "CLASSIFYING":
            return True
        if not await actor_allowed(
            session, task, event.provider, event.actor, actor_type=cycle.feedback.get("actor_type")
        ):
            cycle.decision = "AUTHORITY_REVOKED"
            return True
        if not is_control and cycle.head_sha != task.current_revision:
            cycle.decision = "STALE"
            return True
        cycle.feedback = {
            **cycle.feedback,
            "interpretation": {
                "intent": result.intent.value,
                "confidence": result.confidence,
                "reason": result.reason,
            },
        }
        if (
            result.intent == Intent.APPROVAL
            and not (await read_policy(session, task.team_id)).require_formal_approval
        ):
            cycle.decision = "APPROVAL_INTERPRETED"
        elif result.intent in {Intent.FEEDBACK, Intent.REQUIREMENT_CHANGE}:
            cycle.decision = "FEEDBACK_PENDING"
            await session.flush()
            await apply_pending_feedback(session, task)
        elif result.intent == Intent.IGNORE:
            cycle.decision = "IGNORED"
        elif result.intent in {Intent.PAUSE, Intent.RESUME, Intent.CANCEL}:
            if (
                event.provider == "github"
                and event.actor
                not in (await read_policy(session, task.team_id)).authorized_reviewer_ids
            ):
                cycle.decision = "AUTHORITY_REVOKED"
                return True
            await control_task(
                session, task, Action(result.intent.value), actor=f"{event.provider}:{event.actor}"
            )
            cycle.decision = "COMMAND_APPLIED"
        else:
            cycle.decision = "NEEDS_CLASSIFICATION"
            session.add(
                TaskMessage(
                    task_id=task.id,
                    author_type="SYSTEM",
                    author_name="Interpreter",
                    kind="UPDATE",
                    body="This review message could not be classified reliably. Use explicit /feedback, /pause, /resume or /cancel with the task ID, or submit a formal GitHub review.",
                    context={"review_cycle_id": str(cycle.id)},
                )
            )
            if task.status not in {"PAUSED", "WAITING_HUMAN", "MERGED", "CANCELLED", "FAILED"}:
                await record_transition(
                    session,
                    task.id,
                    Action.BLOCK,
                    expected_version=task.lifecycle_version,
                    actor="interpreter",
                    wait_reason=WaitReason.MISSING_REQUIREMENT,
                )
        if (
            cycle.decision in {"APPROVAL_INTERPRETED", "IGNORED"}
            and task.status == "WAITING_EXTERNAL"
        ):
            repository = await session.get(Repository, task.repository_id)
            if repository is not None:
                await session.flush()
                await github_event(
                    session, task, repository, "interpretation_completed", {"cycle": str(cycle.id)}
                )
    return True
