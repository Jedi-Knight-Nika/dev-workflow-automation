"""Concrete phase controller. Never instantiate native SDKs in this process."""

from dataclasses import replace
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.application.harness import WorkspaceUnavailable
from app.agent_runtime.domain.handoffs import WorkOutcome
from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.infrastructure.docker_harness import DockerHarness
from app.agent_runtime.infrastructure.models import DeveloperSession
from app.agent_runtime.infrastructure.phase_mounts import phase_mounts
from app.agent_runtime.infrastructure.token_efficiency import SqlTokenEfficiency
from app.delivery.infrastructure.git_runner import GitManifest
from app.delivery.infrastructure.git_transport import github_token, run_git
from app.delivery.infrastructure.publication import publish_phase
from app.delivery.infrastructure.workflow import merge_phase
from app.engineering.application.develop import DevelopmentBlocked, DevelopTask, SessionContext
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.infrastructure.consultation import consult, save_consultation_feedback
from app.engineering.infrastructure.developer_failures import block_failed_turn
from app.engineering.infrastructure.developer_request import build_developer_request
from app.engineering.infrastructure.development_setup import (
    admit_development,
    build_developer_manifest,
)
from app.engineering.infrastructure.enrollment import prepare_directories
from app.engineering.infrastructure.phase_context import PhaseContext, load_phase_context
from app.engineering.infrastructure.requirements import current_requirement
from app.engineering.infrastructure.task_models import Task
from app.engineering.infrastructure.validation_phase import validate_phase
from app.platform.configuration.settings import Settings
from app.repositories.infrastructure.models import Repository, RepositoryRuntimeProfile


class SqlPhaseExecutor:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.sessions, self.settings = sessions, settings

    async def runtime_profile(self, task: Task) -> RepositoryRuntimeProfile | None:
        async with self.sessions() as session:
            return (
                await session.get(RepositoryRuntimeProfile, task.repository_id)
                if task.repository_id
                else None
            )

    async def execute(
        self,
        lease: PhaseLease,
        *,
        compaction: bool = False,
        compacted: bool = False,
        continuity: bool = False,
    ) -> Action:
        if lease.action == "MERGE_PR":
            return await merge_phase(self.sessions, lease)
        context = await load_phase_context(
            self.sessions, lease, compaction=compaction, continuity=continuity
        )
        task, native, repository = context.task, context.native, context.repository
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=str(self.settings.docker_socket)),
            base_url="http://docker",
            timeout=self.settings.docker_api_timeout_seconds,
        ) as client:
            if lease.action == "THINKER_TURN":
                plan = await consult(
                    self.sessions, self.settings, client, lease, task, native, "THINKER"
                )
                assert plan is not None
                await save_consultation_feedback(self.sessions, lease, native, *plan)
                return Action.PLAN_READY
            if lease.action == "INTERPRET_EVENT":
                if repository is None:
                    raise PhaseBlocked(WaitReason.MISSING_CONFIGURATION, "Repository is missing")
                return await self._prepare(client, lease, task, native, repository)
            if lease.action == "PUBLISH_PR":
                if repository is None:
                    raise PhaseBlocked(WaitReason.MISSING_CONFIGURATION, "Repository is missing")
                return await publish_phase(
                    self.sessions, self.settings, client, lease, task, native, repository
                )
            if lease.action == "DEVELOPER_TURN":
                return await self._develop(
                    client,
                    lease,
                    context,
                    compaction=compaction,
                    compacted=compacted,
                    continuity=continuity,
                )
            if lease.action == "RUN_VALIDATION":
                return await validate_phase(
                    self.sessions, self.settings, client, lease, task, native, context.team
                )
        raise PhaseBlocked(
            WaitReason.MISSING_CONFIGURATION,
            f"Unknown fixed-lifecycle action: {lease.action}",
        )

    async def _develop(
        self,
        client: httpx.AsyncClient,
        lease: PhaseLease,
        context: PhaseContext,
        *,
        compaction: bool,
        compacted: bool,
        continuity: bool,
    ) -> Action:
        task, native = context.task, context.native
        token_policy = context.token_policy
        from app.agent_runtime.infrastructure.bounded_recovery import (
            schedule_bounded_repair,
            schedule_candidate_validation,
        )

        if await schedule_candidate_validation(self.sessions, lease, native.id):
            return Action.VALIDATE_CANDIDATE
        if task.stage == "DEVELOPING" and await schedule_bounded_repair(
            self.sessions, lease, native.id
        ):
            return Action.BOUNDED_REPAIR
        if (
            task.stage == "FIXING"
            and native.checkpoint.get("next_feedback")
            and not compaction
            and not continuity
        ):
            from app.agent_runtime.infrastructure.repair_generation import prepare_repair

            native = await prepare_repair(self.sessions, lease, native)
        bounded_repair = native.checkpoint.get("bounded_repair_job_id") == str(lease.job_id)
        if bounded_repair:
            token_policy = replace(
                token_policy,
                mode="ENFORCE",
                reasoning_effort="low",
                first_edit_warning_tokens=20000,
                exploration_hard_tokens=50000,
                no_progress_tokens=20000,
                max_turn_input_tokens=80000,
                automatic_rollover=False,
            )
        supervisor_guidance = ""
        from app.agent_runtime.infrastructure.patch_recovery import (
            can_resume_patch,
            needs_source_selection,
        )

        async with self.sessions() as session:
            patch_resume_allowed = (
                not compaction
                and not continuity
                and not native.checkpoint.get("next_feedback")
                and await can_resume_patch(session, native, task.requirement_version)
            )
            relocalize = patch_resume_allowed and await needs_source_selection(session, native)
        if (
            self.settings.supervisor_enabled
            and (not patch_resume_allowed or relocalize)
            and not compaction
            and not continuity
            and not (native.harness == "patch" and task.stage == "FIXING")
        ):
            from app.supervisor.infrastructure.service import supervise

            decision = await supervise(self.sessions, self.settings, lease, native.id)
            if decision.action == "WAIT_HUMAN":
                raise PhaseBlocked(WaitReason.MISSING_REQUIREMENT, decision.assessment)
            supervisor_guidance = decision.developer_guidance()
        continued = await self._continue_session(
            lease,
            task,
            native,
            token_policy,
            compaction=compaction,
            compacted=compacted,
            continuity=continuity,
        )
        if continued is not None:
            return continued
        admission = await admit_development(
            self.sessions,
            self.settings,
            lease,
            context,
            native,
            bounded_repair=bounded_repair,
            compaction=compaction,
            continuity=continuity,
        )
        store = admission.store
        async with self.sessions() as session:
            try:
                request = "ORIGINAL REQUIREMENT (authoritative):\n" + await current_requirement(
                    session, task
                )
            except ValueError as exc:
                raise PhaseBlocked(WaitReason.MISSING_REQUIREMENT, str(exc)) from exc
        prepared = build_developer_request(
            task,
            native,
            request,
            supervisor_guidance=supervisor_guidance,
            patch_resume_allowed=patch_resume_allowed,
            compaction=compaction,
            continuity=continuity,
        )
        manifest = build_developer_manifest(
            self.settings,
            context,
            native,
            token_policy,
            prepared,
            admission.allowance,
            bounded_repair=bounded_repair,
            compaction=compaction,
            continuity=continuity,
        )
        mounts = phase_mounts(
            self.settings, lease, native, compaction=compaction, continuity=continuity
        )
        environment = {
            {
                "openai": "OPENAI_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
            }[native.provider]: admission.credential,
            "HTTPS_PROXY": self.settings.developer_egress_proxy,
            "HTTP_PROXY": self.settings.developer_egress_proxy,
        }
        runtime = await self.runtime_profile(task)

        async def handle_supervision(anomaly: dict[str, object]) -> dict[str, object]:
            from app.supervisor.infrastructure.service import supervise

            try:
                result = await supervise(
                    self.sessions, self.settings, lease, native.id, anomaly=anomaly
                )
                action = result.action if result.action in {"CONTINUE", "NUDGE"} else "STOP"
                return {"action": action, "message": result.execution_brief[:3000]}
            except (ValueError, RuntimeError, httpx.HTTPError, TimeoutError):
                return {
                    "action": "STOP",
                    "message": "Supervisor unavailable; preserve session for inspection",
                }

        harness = DockerHarness(
            client,
            mounts=mounts,
            manifest=manifest,
            image=runtime.developer_image_ref
            if runtime
            else self.settings.developer_container_image,
            network=self.settings.developer_container_network,
            environment=environment,
            job_id=lease.job_id,
            lease_token=lease.token,
            on_progress=store.progress,
            on_supervision=handle_supervision if manifest.supervision_enabled else None,
        )
        try:
            receipt = await DevelopTask(harness, store, admission.budget).execute(
                SessionContext(
                    task.id, native.native_session_id, task.requirement_version, prepared.request
                ),
                feedback=prepared.feedback,
                compaction=compaction,
            )
        except DevelopmentBlocked as exc:
            raise PhaseBlocked(WaitReason.BUDGET_EXHAUSTED, str(exc)) from exc
        except WorkspaceUnavailable as exc:
            raise PhaseBlocked(WaitReason.MISSING_CONFIGURATION, str(exc)) from exc
        if receipt.status != "completed":
            if receipt.failure_code == "TURN_INPUT_LIMIT" and await schedule_candidate_validation(
                self.sessions, lease, native.id
            ):
                return Action.VALIDATE_CANDIDATE
            if receipt.failure_code == "TURN_INPUT_LIMIT" and await schedule_bounded_repair(
                self.sessions, lease, native.id
            ):
                return Action.BOUNDED_REPAIR
            block_failed_turn(receipt, native.harness)
        outcome = WorkOutcome(receipt.result.payload["outcome"]) if receipt.result else None
        if outcome == WorkOutcome.NEEDS_HUMAN:
            raise PhaseBlocked(WaitReason.MISSING_REQUIREMENT, receipt.summary[-1000:])
        if outcome == WorkOutcome.FAILED:
            raise PhaseBlocked(WaitReason.RUNTIME_FAILURE, "Developer reported a failed result")
        if (
            outcome == WorkOutcome.MILESTONE_COMPLETE
            or outcome is None
            and receipt.summary.startswith("MILESTONE_COMPLETE\n")
        ):
            if not token_policy.automatic_rollover or token_policy.mode != "ENFORCE":
                raise PhaseBlocked(
                    WaitReason.MISSING_REQUIREMENT,
                    "Milestone complete; approve a checkpoint before continuing",
                )
            try:
                async with self.sessions() as session:
                    await SqlTokenEfficiency(session).rollover(
                        task.id,
                        task.requirement_version,
                        receipt.summary[len("MILESTONE_COMPLETE\n") :][:1800],
                        job_id=lease.job_id,
                        lease_token=lease.token,
                    )
            except (ValueError, RuntimeError, OSError) as exc:
                raise PhaseBlocked(
                    WaitReason.MISSING_REQUIREMENT,
                    "Milestone checkpoint blocked; retained native context",
                ) from exc
            return await self.execute(lease)
        if (
            outcome == WorkOutcome.NEEDS_PLAN
            or outcome is None
            and receipt.summary.strip().split("\n", 1)[0].strip() == "NEEDS_PLAN"
        ):
            return Action.NEEDS_PLAN
        return Action.IMPLEMENTED

    async def _continue_session(
        self,
        lease: PhaseLease,
        task: Task,
        native: DeveloperSession,
        token_policy: TokenEfficiencyPolicy,
        *,
        compaction: bool,
        compacted: bool,
        continuity: bool,
    ) -> Action | None:
        checkpoint_digest = native.checkpoint.get("rollover_digest")
        if (
            checkpoint_digest
            and native.checkpoint.get("continuity_acknowledged") != checkpoint_digest
            and not continuity
        ):
            if native.native_session_id:
                raise PhaseBlocked(
                    WaitReason.MISSING_REQUIREMENT,
                    "Checkpoint acknowledgement failed; no automatic paid retry",
                )
            await self.execute(lease, continuity=True)
            return await self.execute(lease)
        threshold = self.settings.developer_compact_before_feedback_tokens
        active_context = (native.checkpoint.get("token_efficiency") or {}).get(
            "active_context_estimate"
        )
        if (
            not compaction
            and not continuity
            and native.native_session_id
            and native.checkpoint.get("next_feedback")
            and token_policy.automatic_rollover
            and native.harness not in {"responses", "patch"}
            and token_policy.mode == "ENFORCE"
            and active_context is not None
            and active_context >= token_policy.active_context_soft_tokens
        ):
            try:
                async with self.sessions() as session:
                    await SqlTokenEfficiency(session).rollover(
                        task.id,
                        task.requirement_version,
                        str(
                            native.checkpoint.get("summary")
                            or "Continue from current validated code and pending review feedback."
                        )[:1800],
                        job_id=lease.job_id,
                        lease_token=lease.token,
                    )
            except (ValueError, RuntimeError, OSError) as exc:
                raise PhaseBlocked(
                    WaitReason.MISSING_REQUIREMENT,
                    "CHECKPOINT_PERSISTENCE_FAILED; retained native context",
                ) from exc
            return await self.execute(lease)
        if (
            not compaction
            and not compacted
            and threshold
            and native.harness not in {"responses", "patch"}
            and native.native_session_id
            and active_context is not None
            and active_context >= threshold
            and int(native.checkpoint.get("compaction_count", 0)) < token_policy.max_compactions
            and native.checkpoint.get("next_feedback")
        ):
            # Two separately metered runs, one native session. The next
            # call reloads usage and cannot reuse the compaction reserve.
            await self.execute(lease, compaction=True)
            return await self.execute(lease, compacted=True)
        return None

    async def _prepare(
        self,
        client: httpx.AsyncClient,
        lease: PhaseLease,
        task: Task,
        native: DeveloperSession,
        repository: Repository,
    ) -> Action:
        if native.checkpoint.get("base_sha"):
            return Action.START
        prepare_directories(
            Path(native.workspace_path), Path(native.state_path), str(task.id), self.settings
        )
        mounts = phase_mounts(self.settings, lease, native)
        async with self.sessions() as session:
            token = await github_token(session)
        result = await run_git(
            client,
            self.settings,
            mounts,
            GitManifest(
                operation="prepare",
                owner=repository.owner,
                repository=repository.name,
                branch=task.branch_name or "",
                base_branch=repository.default_branch,
            ),
            token,
            f"prepare-{lease.job_id}-{lease.token}",
        )
        async with self.sessions.begin() as session:
            current = await session.get(Task, task.id, with_for_update=True)
            state = await session.get(DeveloperSession, native.id, with_for_update=True)
            if (
                current is None
                or state is None
                or current.lifecycle_version != lease.lifecycle_version
            ):
                raise ValueError("Task changed while preparing its workspace")
            current.current_revision = result["head_sha"]
            state.last_revision = result["head_sha"]
            state.checkpoint = {
                **state.checkpoint,
                "base_sha": result["head_sha"],
                "base_branch": repository.default_branch,
            }
        return Action.START
