"""Operator-only metadata change. No SDK calls, transcript replay, or usage reset."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.application.sessions import ChangeSession, SessionConflict, SessionView
from app.agent_runtime.domain.session_changes import (
    SessionChangeMode,
    can_keep_native,
    handoff_request,
)
from app.agent_runtime.infrastructure.versions import HARNESS_VERSIONS
from app.db.models import (
    AIRun,
    DeveloperSession,
    Job,
    JobState,
    Task,
    TaskEvent,
    Team,
    TeamAgentProfile,
)


class SqlSessionAdministration:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load(
        self, task_id: UUID, *, lock: bool = False
    ) -> tuple[Task, DeveloperSession, TeamAgentProfile] | None:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise LookupError("Task not found")
        team_id = task.team_id
        if lock and team_id:
            # Same Team -> Task order as cost reservations/profile configuration.
            await self.session.get(Team, team_id, with_for_update=True)
        if lock:
            task = await self.session.get(
                Task, task_id, with_for_update=True, populate_existing=True
            )
            if task is None or task.team_id != team_id:
                raise SessionConflict("Task ownership changed; reload")
        native_query = (
            select(DeveloperSession)
            .where(DeveloperSession.task_id == task_id)
            .order_by(DeveloperSession.generation.desc())
            .limit(1)
        )
        native = await self.session.scalar(native_query.with_for_update() if lock else native_query)
        if task.execution_version != 2 or native is None:
            return None
        profile = await self.session.scalar(
            select(TeamAgentProfile).where(
                TeamAgentProfile.team_id == team_id, TeamAgentProfile.role_kind == "DEVELOPER"
            )
        )
        if profile is None:
            raise SessionConflict("The task needs its Team's fixed Developer profile")
        return task, native, profile

    async def _blocker(self, task: Task, native: DeveloperSession) -> str | None:
        if task.archived_at or task.manual_takeover:
            return "Release manual takeover and use a non-archived task first"
        if task.status not in {"PAUSED", "WAITING_HUMAN"}:
            return "Pause the task before changing its native session"
        if native.state == "RUNNING" or await self.session.scalar(
            select(Job.id)
            .where(Job.task_id == task.id, Job.state.in_([JobState.CLAIMED, JobState.RUNNING]))
            .limit(1)
        ):
            return "Wait for the active worker to stop and persist its receipt"
        if await self.session.scalar(
            select(AIRun.id)
            .where(
                AIRun.task_id == task.id,
                or_(
                    AIRun.status == "RUNNING",
                    func.coalesce(AIRun.provider_cost_usd, AIRun.calculated_cost_usd).is_(None),
                ),
            )
            .limit(1)
        ):
            return "Reconcile running or unknown-cost turns before changing sessions"
        return None

    async def _view(
        self, task: Task, native: DeveloperSession, profile: TeamAgentProfile
    ) -> SessionView:
        return SessionView(
            native.id,
            native.generation,
            bool(native.native_session_id),
            native.harness,
            native.provider,
            native.model,
            native.state,
            task.status or "NEW",
            task.lifecycle_version,
            profile.version,
            profile.harness or "",
            profile.provider,
            profile.model,
            can_keep_native(
                native.harness, profile.harness or "", native.provider, profile.provider
            ),
            await self._blocker(task, native),
        )

    async def read(self, task_id: UUID) -> SessionView | None:
        loaded = await self._load(task_id)
        return await self._view(*loaded) if loaded else None

    async def change(self, task_id: UUID, command: ChangeSession) -> SessionView:
        loaded = await self._load(task_id, lock=True)
        if loaded is None:
            raise SessionConflict("Enroll the task before changing a native session")
        task, native, profile = loaded
        if (
            native.id != command.session_id
            or task.lifecycle_version != command.lifecycle_version
            or profile.version != command.profile_version
        ):
            raise SessionConflict("Task, session or profile changed; reload before applying")
        blocker = await self._blocker(task, native)
        if blocker:
            raise SessionConflict(blocker)
        if not profile.enabled or (profile.harness, profile.provider) not in {
            ("codex", "openai"),
            ("claude", "anthropic"),
        }:
            raise SessionConflict("Configure an enabled native Developer profile first")
        assert profile.harness is not None
        old = {
            "session_id": str(native.id),
            "harness": native.harness,
            "model": native.model,
            "provider": native.provider,
            "generation": native.generation,
        }
        checkpoint = dict(native.checkpoint)
        if command.mode == SessionChangeMode.KEEP_NATIVE:
            if not can_keep_native(
                native.harness, profile.harness, native.provider, profile.provider
            ):
                raise SessionConflict("This change requires an explicit new-session handoff")
            if (native.model, native.profile_id) == (profile.model, profile.id):
                raise SessionConflict("The native session already uses this profile/model")
            if native.native_session_id:
                delta = (
                    f"Operator model change: {native.model} -> {profile.model}. "
                    f"Reason: {command.reason.strip()}. Continue the same task on the existing checkout."
                )
                feedback = str(checkpoint.get("next_feedback") or "")
                if len(delta) + len(feedback) + 2 > 24000:
                    raise SessionConflict(
                        "Pending feedback is too long; shorten it explicitly first"
                    )
                checkpoint["next_feedback"] = f"{delta}\n\n{feedback}".strip()
            native.model, native.profile_id = profile.model, profile.id
            native.checkpoint = checkpoint
        else:
            # Carry only the bounded checkpoint and the outstanding delta, not
            # a concatenated transcript. Historical sessions/runs remain intact.
            note = command.reason.strip()
            summary = str(checkpoint.get("summary") or "")[-4000:]
            handoff_request(
                f"{task.title}\n\n{task.description}".strip(),
                summary,
                note,
                str(checkpoint.get("next_feedback") or ""),
            )
            successor = DeveloperSession(
                task_id=task.id,
                profile_id=profile.id,
                generation=native.generation + 1,
                harness=profile.harness,
                harness_version=HARNESS_VERSIONS[profile.harness],
                provider=profile.provider,
                model=profile.model,
                workspace_path=native.workspace_path,
                state_path=native.state_path,
                requirement_version=task.requirement_version,
                last_revision=native.last_revision,
                checkpoint={
                    **{
                        key: checkpoint[key]
                        for key in ("base_sha", "base_branch", "next_feedback")
                        if key in checkpoint
                    },
                    "handoff": {
                        "from_session_id": str(native.id),
                        "summary": summary,
                        "note": note,
                    },
                },
            )
            native.state = "SUPERSEDED"
            self.session.add(successor)
            native = successor
        task.lifecycle_version += 1
        await self.session.flush()
        self.session.add(
            TaskEvent(
                task_id=task.id,
                source="user",
                event_type="DEVELOPER_SESSION_CHANGED",
                payload={
                    "actor": "user",
                    "mode": command.mode.value,
                    "reason": command.reason.strip(),
                    "previous": old,
                    "session_id": str(native.id),
                    "model": native.model,
                    "provider": native.provider,
                    "harness": native.harness,
                    "lifecycle_version": task.lifecycle_version,
                    "usage_reset": False,
                },
            )
        )
        result = await self._view(task, native, profile)
        await self.session.commit()
        # Do not resume, enqueue, call a provider or touch any native files here.
        return result
