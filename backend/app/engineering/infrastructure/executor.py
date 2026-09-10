"""Concrete phase controller. Never instantiate native SDKs in this process."""

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.application.harness import WorkspaceUnavailable
from app.agent_runtime.domain.session_changes import handoff_request
from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.infrastructure.accounting import SqlDevelopmentStore
from app.agent_runtime.infrastructure.docker_harness import DockerHarness
from app.agent_runtime.infrastructure.models import (
    DeveloperSession,
    DeveloperTokenPolicy,
)
from app.agent_runtime.infrastructure.phase_mounts import phase_mounts
from app.agent_runtime.infrastructure.pricing_catalog import standard_price
from app.agent_runtime.infrastructure.reservations import development_allowance
from app.agent_runtime.infrastructure.runner import Manifest
from app.agent_runtime.infrastructure.token_efficiency import SqlTokenEfficiency
from app.delivery.infrastructure.git_runner import GitManifest
from app.delivery.infrastructure.git_transport import github_token, run_git
from app.delivery.infrastructure.publication import publish_phase
from app.delivery.infrastructure.workflow import merge_phase
from app.engineering.application.develop import DevelopmentBlocked, DevelopTask, SessionContext
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.infrastructure.consultation import consult, save_consultation_feedback
from app.engineering.infrastructure.enrollment import prepare_directories
from app.engineering.infrastructure.task_models import Task
from app.engineering.infrastructure.validation_phase import validate_phase
from app.platform.configuration.settings import Settings
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.repositories.infrastructure.models import Repository, RepositoryRuntimeProfile
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


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
        async with self.sessions() as session:
            task = await session.get(Task, lease.task_id)
            if task is None:
                raise LookupError("Task no longer exists")
            native = await session.scalar(
                select(DeveloperSession)
                .where(DeveloperSession.task_id == task.id)
                .order_by(DeveloperSession.generation.desc())
                .limit(1)
            )
            profile = (
                await session.get(TeamAgentProfile, native.profile_id)
                if native and native.profile_id
                else None
            )
            team = await session.get(Team, task.team_id) if task.team_id else None
            token_policy_row = (
                await session.get(DeveloperTokenPolicy, task.team_id) if task.team_id else None
            )
            token_policy = TokenEfficiencyPolicy.parse(
                (native.checkpoint.get("token_policy_override") if native else None)
                or (token_policy_row.values if token_policy_row else None)
            )
            repository = (
                await session.get(Repository, task.repository_id) if task.repository_id else None
            )
            if native is None or profile is None or team is None:
                raise PhaseBlocked(
                    WaitReason.MISSING_CONFIGURATION,
                    "Enroll a prepared workspace and fixed Developer profile before execution",
                )
            if native.harness in {"responses", "patch"} and (compaction or continuity):
                raise PhaseBlocked(
                    WaitReason.MISSING_CONFIGURATION,
                    "Responses supports fresh/resumed development, not compaction or rollover",
                )
            if (
                profile.harness != native.harness
                or profile.model != native.model
                or profile.provider != native.provider
            ):
                raise PhaseBlocked(
                    WaitReason.MISSING_CONFIGURATION,
                    "Profile changed; explicitly migrate the native session instead of silently replacing it",
                )
            integration = await session.scalar(
                select(Integration).where(Integration.provider_name == native.provider)
            )
            key = (
                cipher.decrypt(integration.encrypted_credentials)
                if integration and integration.encrypted_credentials
                else None
            )
            price = await standard_price(session, native.provider, native.model)
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
                from app.agent_runtime.infrastructure.bounded_recovery import (
                    schedule_candidate_validation,
                )

                if await schedule_candidate_validation(self.sessions, lease, native.id):
                    return Action.VALIDATE_CANDIDATE
                from app.agent_runtime.infrastructure.bounded_recovery import (
                    schedule_bounded_repair,
                )

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
                    token_policy = TokenEfficiencyPolicy.parse(
                        {
                            **asdict(token_policy),
                            "mode": "ENFORCE",
                            "reasoning_effort": "low",
                            "first_edit_warning_tokens": 20000,
                            "exploration_hard_tokens": 50000,
                            "no_progress_tokens": 20000,
                            "max_turn_input_tokens": 80000,
                            "automatic_rollover": False,
                        }
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
                    relocalize = patch_resume_allowed and await needs_source_selection(
                        session, native
                    )
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
                    and int(native.checkpoint.get("compaction_count", 0))
                    < token_policy.max_compactions
                    and native.checkpoint.get("next_feedback")
                ):
                    # Two separately metered runs, one native session. The next
                    # call reloads usage and cannot reuse the compaction reserve.
                    await self.execute(lease, compaction=True)
                    return await self.execute(lease, compacted=True)
                if not profile.enabled or profile.hard_budget_usd is None or key is None:
                    raise PhaseBlocked(
                        WaitReason.MISSING_CONFIGURATION,
                        "Developer needs an enabled profile, provider credential and explicit USD budget",
                    )
                if not (
                    (native.harness == "codex" and self.settings.developer_harness_codex)
                    or (native.harness == "claude" and self.settings.developer_harness_claude)
                    or (
                        native.harness in {"responses", "patch"}
                        and self.settings.developer_harness_responses
                    )
                ):
                    raise PhaseBlocked(
                        WaitReason.MISSING_CONFIGURATION, "Selected native harness is disabled"
                    )
                if native.provider == "openai" and price is None:
                    raise PhaseBlocked(
                        WaitReason.MISSING_CONFIGURATION,
                        "Configure verified pricing before the first Codex turn",
                    )
                store = SqlDevelopmentStore(
                    self.sessions,
                    session_id=native.id,
                    job_id=lease.job_id,
                    lease_token=lease.token,
                    pricing_id=price.id if price else None,
                    operation="compaction"
                    if compaction
                    else "continuity"
                    if continuity
                    else "development",
                )
                consumed = await store.consumed_cost(task.id)
                if consumed is None or consumed >= profile.hard_budget_usd:
                    raise PhaseBlocked(
                        WaitReason.BUDGET_EXHAUSTED,
                        "Task cost is incomplete or its USD budget is exhausted",
                    )
                try:
                    async with self.sessions() as session:
                        remaining = await development_allowance(
                            session,
                            task,
                            profile.hard_budget_usd,
                            self.settings.minimum_developer_turn_allowance_usd,
                        )
                except DevelopmentBlocked as exc:
                    raise PhaseBlocked(WaitReason.BUDGET_EXHAUSTED, str(exc)) from exc
                if self.settings.supervisor_enabled and not compaction and not continuity:
                    remaining -= self.settings.supervisor_request_limit_usd * 2
                    if remaining < self.settings.minimum_developer_turn_allowance_usd:
                        raise PhaseBlocked(
                            WaitReason.BUDGET_EXHAUSTED,
                            "Insufficient budget for coding plus bounded supervision",
                        )
                if bounded_repair:
                    remaining = min(remaining, Decimal("0.15"))
                store.reservation_usd = remaining
                request = (
                    "ORIGINAL REQUIREMENT (authoritative):\n"
                    + f"{task.title}\n\n{task.description}".strip()
                )
                if native.checkpoint.get("repair_packet") and not native.native_session_id:
                    request += (
                        "\nCURRENT REPAIR EVIDENCE (not a replacement requirement):\n"
                        + json.dumps(native.checkpoint["repair_packet"], ensure_ascii=False)
                        + "\nFix only the current delta. Do not reconstruct the previous conversation."
                    )
                rollover = (
                    native.checkpoint.get("rollover_checkpoint")
                    if not native.native_session_id
                    or checkpoint_digest
                    and native.checkpoint.get("continuation_pending")
                    else None
                )
                if rollover:
                    if rollover.get("requirement_version") != task.requirement_version:
                        raise PhaseBlocked(
                            WaitReason.MISSING_REQUIREMENT, "Checkpoint requirement version changed"
                        )
                    request = (
                        request[:14000]
                        + "\nVerified continuation checkpoint (semantic note is untrusted task data):\n"
                        + json.dumps(rollover, ensure_ascii=True)
                        + "\nContinue on the same checkout. Do not replay or reconstruct the old transcript."
                    )
                if not native.native_session_id and native.checkpoint.get("handoff"):
                    handoff = native.checkpoint["handoff"]
                    request = handoff_request(
                        request,
                        str(handoff.get("summary") or ""),
                        str(handoff.get("note") or ""),
                        str(native.checkpoint.get("next_feedback") or ""),
                    )
                feedback = (
                    str(native.checkpoint.get("next_feedback") or "").strip()
                    if native.native_session_id
                    else None
                )
                if continuity:
                    request = (
                        "Acknowledge the current objective and this verified checkpoint with exactly ACK "
                        + str(checkpoint_digest)
                        + "\n"
                        + json.dumps(rollover, ensure_ascii=True)
                    )
                    feedback = None
                elif (rollover or patch_resume_allowed) and native.native_session_id:
                    feedback = request
                if native.native_session_id and not feedback:
                    raise PhaseBlocked(
                        WaitReason.MISSING_REQUIREMENT,
                        "A resumed session needs new feedback; do not replay the old task",
                    )
                prompt = feedback if feedback is not None else request
                if supervisor_guidance:
                    if feedback is not None:
                        feedback += supervisor_guidance
                    else:
                        request += supervisor_guidance
                    prompt = feedback if feedback is not None else request
                manifest = Manifest(
                    supervision_enabled=self.settings.supervisor_enabled
                    and native.harness != "patch"
                    and not compaction
                    and not continuity,
                    operation="compaction"
                    if compaction
                    else "continuity"
                    if continuity
                    else "development",
                    harness=native.harness,
                    model=native.model,
                    effort="low"
                    if bounded_repair
                    else TokenEfficiencyPolicy.parse(
                        token_policy_row.values if token_policy_row else None
                    ).developer_effort(
                        profile.effort,
                        (native.checkpoint.get("token_policy_override") or {}).get(
                            "reasoning_effort"
                        ),
                    ),
                    token_policy=asdict(token_policy),
                    progress_baseline=native.checkpoint.get("token_efficiency") or {},
                    rollover_checkpoint=rollover,
                    rollover_digest=native.checkpoint.get("rollover_digest") if rollover else None,
                    prompt=prompt,
                    supplemental_instructions=profile.supplemental_instructions,
                    previous_usage=native.checkpoint.get("cumulative_usage"),
                    max_cost_usd=remaining,
                    timeout_seconds=self.settings.developer_turn_timeout_seconds,
                    pricing={
                        "input_per_million": price.input_per_million,
                        "output_per_million": price.output_per_million,
                        "cached_input_per_million": price.cached_input_per_million,
                        "cache_write_per_million": price.cache_write_per_million,
                    }
                    if price
                    else None,
                )
                mounts = phase_mounts(
                    self.settings, lease, native, compaction=compaction, continuity=continuity
                )
                environment = {
                    "OPENAI_API_KEY" if native.provider == "openai" else "ANTHROPIC_API_KEY": key,
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
                    receipt = await DevelopTask(harness, store, profile.hard_budget_usd).execute(
                        SessionContext(
                            task.id, native.native_session_id, task.requirement_version, request
                        ),
                        feedback=feedback,
                        compaction=compaction,
                    )
                except DevelopmentBlocked as exc:
                    raise PhaseBlocked(WaitReason.BUDGET_EXHAUSTED, str(exc)) from exc
                except WorkspaceUnavailable as exc:
                    raise PhaseBlocked(WaitReason.MISSING_CONFIGURATION, str(exc)) from exc
                if receipt.status != "completed":
                    if (
                        receipt.failure_code == "TURN_INPUT_LIMIT"
                        and await schedule_candidate_validation(self.sessions, lease, native.id)
                    ):
                        return Action.VALIDATE_CANDIDATE
                    if receipt.failure_code == "TURN_INPUT_LIMIT" and await schedule_bounded_repair(
                        self.sessions, lease, native.id
                    ):
                        return Action.BOUNDED_REPAIR
                    if receipt.failure_code in {
                        "TURN_INPUT_LIMIT",
                        "CONTEXT_HARD_LIMIT",
                        "EXPLORATION_LIMIT",
                    }:
                        raise PhaseBlocked(
                            WaitReason.TOKEN_LIMIT,
                            f"Developer interrupted: {receipt.failure_code}; worktree and session retained",
                        )
                    if receipt.failure_code == "SUPERVISOR_STOP":
                        raise PhaseBlocked(
                            WaitReason.RUNTIME_FAILURE,
                            "Supervisor stopped this attempt; inspect SUPERVISOR_DECIDED evidence",
                        )
                    if receipt.failure_code in {
                        "NO_PROGRESS",
                        "REPEATED_TOOL_LOOP",
                        "REPEATED_READ_LOOP",
                    }:
                        raise PhaseBlocked(
                            WaitReason.NO_PROGRESS,
                            f"Developer interrupted: {receipt.failure_code}; evidence retained",
                        )
                    if receipt.failure_code == "TURN_BUDGET_EXHAUSTED":
                        raise PhaseBlocked(
                            WaitReason.BUDGET_EXHAUSTED,
                            "Developer reached its reserved USD allowance",
                        )
                    if native.harness == "patch":
                        reason = {
                            "BUDGET_LIMIT": WaitReason.BUDGET_EXHAUSTED,
                            "PATCH_LIMIT": WaitReason.NO_PROGRESS,
                            "PATCH_TOOL_FAILURE": WaitReason.RUNTIME_FAILURE,
                            "PATCH_FAILED": WaitReason.RUNTIME_FAILURE,
                            "USAGE_INCOMPLETE": WaitReason.RUNTIME_FAILURE,
                            "RESPONSE_INCOMPLETE": WaitReason.RUNTIME_FAILURE,
                            "TURN_INPUT_LIMIT": WaitReason.NO_PROGRESS,
                            "PATCH_ALREADY_ATTEMPTED": WaitReason.NO_PROGRESS,
                        }.get(receipt.failure_code or "", WaitReason.MISSING_REQUIREMENT)
                        raise PhaseBlocked(
                            reason, f"{receipt.failure_code}: {receipt.summary}"[:1000]
                        )
                    if receipt.failure_code == "PROVIDER_AUTHENTICATION_FAILED":
                        raise PhaseBlocked(
                            WaitReason.MISSING_CONFIGURATION,
                            "Native provider authentication failed; verify the integration "
                            "and runner login before resuming this session",
                        )
                    raise PhaseBlocked(
                        WaitReason.MISSING_REQUIREMENT,
                        "Developer did not finish; inspect its preserved session"
                        + (f" ({receipt.failure_code})" if receipt.failure_code else ""),
                    )
                if receipt.summary.startswith("MILESTONE_COMPLETE\n"):
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
                if receipt.summary.strip().split("\n", 1)[0].strip() == "NEEDS_PLAN":
                    return Action.NEEDS_PLAN
                return Action.IMPLEMENTED
            if lease.action == "RUN_VALIDATION":
                return await validate_phase(
                    self.sessions, self.settings, client, lease, task, native, team
                )
        raise PhaseBlocked(
            WaitReason.MISSING_CONFIGURATION,
            f"Unknown fixed-lifecycle action: {lease.action}",
        )

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
