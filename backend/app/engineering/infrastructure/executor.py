"""Concrete phase controller. Never instantiate native SDKs in this process."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.domain.session_changes import handoff_request
from app.agent_runtime.infrastructure.accounting import SqlDevelopmentStore
from app.agent_runtime.infrastructure.container import RunnerMounts, validation_container_spec
from app.agent_runtime.infrastructure.container_job import run_container_job
from app.agent_runtime.infrastructure.docker_harness import DockerHarness, atomic_json
from app.agent_runtime.infrastructure.models import DeveloperSession, PricingCatalog
from app.agent_runtime.infrastructure.runner import Manifest
from app.delivery.infrastructure.git_runner import GitManifest
from app.delivery.infrastructure.git_transport import github_token, run_git
from app.delivery.infrastructure.github import GitHubDelivery, github_client
from app.delivery.infrastructure.workflow import delivery_gate, merge_phase
from app.engineering.application.develop import DevelopmentBlocked, DevelopTask, SessionContext
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.infrastructure.consultation import consult, save_consultation_feedback
from app.engineering.infrastructure.enrollment import prepare_directories
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Task
from app.engineering.infrastructure.validator_runner import ValidationManifest
from app.platform.configuration.settings import Settings
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


class SqlPhaseExecutor:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.sessions, self.settings = sessions, settings

    def _mounts(
        self, lease: PhaseLease, native: DeveloperSession, *, compaction: bool = False
    ) -> RunnerMounts:
        root = self.settings.harness_control_root.resolve()
        directory = (
            root / str(lease.task_id) / (str(lease.token) + ("-compact" if compaction else ""))
        )
        directory.mkdir(parents=True, exist_ok=False)
        lock_path = root / str(lease.task_id) / "workspace.lock"
        try:
            lock_path.touch(exist_ok=False)
        except FileExistsError:
            pass  # Never replace an inode a surviving runner may still have locked.
        return RunnerMounts(
            lease.task_id,
            Path(native.workspace_path),
            Path(native.state_path),
            directory / "task.json",
            self.settings.workspace_root.resolve() / "tasks",
            self.settings.harness_state_root.resolve(),
            root,
        )

    async def execute(
        self, lease: PhaseLease, *, compaction: bool = False, compacted: bool = False
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
            repository = (
                await session.get(Repository, task.repository_id) if task.repository_id else None
            )
            if native is None or profile is None or team is None:
                raise PhaseBlocked(
                    WaitReason.MISSING_CONFIGURATION,
                    "Enroll a prepared workspace and fixed Developer profile before execution",
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
            price = await session.scalar(
                select(PricingCatalog)
                .where(
                    PricingCatalog.provider == native.provider,
                    PricingCatalog.model == native.model,
                    PricingCatalog.context_tier == "standard",
                    PricingCatalog.service_tier == "standard",
                    PricingCatalog.effective_at <= datetime.now(UTC),
                )
                .order_by(PricingCatalog.effective_at.desc())
                .limit(1)
            )
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
                return await self._publish(client, lease, task, native, repository)
            if lease.action == "DEVELOPER_TURN":
                threshold = self.settings.developer_compact_before_feedback_tokens
                cumulative_input = (native.checkpoint.get("cumulative_usage") or {}).get(
                    "input_tokens"
                ) or 0
                if (
                    not compaction
                    and not compacted
                    and threshold
                    and native.native_session_id
                    and cumulative_input - int(native.checkpoint.get("compacted_input_tokens") or 0)
                    >= threshold
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
                    operation="compaction" if compaction else "development",
                )
                consumed = await store.consumed_cost(task.id)
                if consumed is None or consumed >= profile.hard_budget_usd:
                    raise PhaseBlocked(
                        WaitReason.BUDGET_EXHAUSTED,
                        "Task cost is incomplete or its USD budget is exhausted",
                    )
                async with self.sessions() as session:
                    policy = await read_policy(session, team.id)
                remaining = min(profile.hard_budget_usd, policy.task_budget_usd) - consumed
                if remaining <= 0:
                    raise PhaseBlocked(WaitReason.BUDGET_EXHAUSTED, "Task USD budget is exhausted")
                store.reservation_usd = remaining
                request = f"{task.title}\n\n{task.description}".strip()
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
                if native.native_session_id and not feedback:
                    raise PhaseBlocked(
                        WaitReason.MISSING_REQUIREMENT,
                        "A resumed session needs new feedback; do not replay the old task",
                    )
                prompt = feedback if feedback is not None else request
                manifest = Manifest(
                    operation="compaction" if compaction else "development",
                    harness=native.harness,
                    model=native.model,
                    effort=profile.effort,
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
                mounts = self._mounts(lease, native, compaction=compaction)
                environment = {
                    "OPENAI_API_KEY" if native.provider == "openai" else "ANTHROPIC_API_KEY": key,
                    "HTTPS_PROXY": self.settings.developer_egress_proxy,
                    "HTTP_PROXY": self.settings.developer_egress_proxy,
                }
                harness = DockerHarness(
                    client,
                    mounts=mounts,
                    manifest=manifest,
                    image=self.settings.developer_container_image,
                    network=self.settings.developer_container_network,
                    environment=environment,
                    job_id=lease.job_id,
                    lease_token=lease.token,
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
                if receipt.status != "completed":
                    raise PhaseBlocked(
                        WaitReason.MISSING_REQUIREMENT,
                        "Developer did not finish; inspect its preserved session",
                    )
                if receipt.summary.strip().split("\n", 1)[0].strip() == "NEEDS_PLAN":
                    return Action.NEEDS_PLAN
                return Action.IMPLEMENTED
            if lease.action == "RUN_VALIDATION":
                return await self._validate(client, lease, task, native, team)
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
        mounts = self._mounts(lease, native)
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

    async def _publish(
        self,
        client: httpx.AsyncClient,
        lease: PhaseLease,
        task: Task,
        native: DeveloperSession,
        repository: Repository,
    ) -> Action:
        async with self.sessions() as session:
            _, _, validated = await delivery_gate(session, task, repository)
            token = await github_token(session)
        if not validated:
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION,
                "Publication requires passing validation at the current requirement and SHA",
            )
        mounts = self._mounts(lease, native)
        await run_git(
            client,
            self.settings,
            mounts,
            GitManifest(
                operation="publish",
                owner=repository.owner,
                repository=repository.name,
                branch=task.branch_name or "",
                base_branch=str(native.checkpoint.get("base_branch") or repository.default_branch),
                expected_sha=validated,
            ),
            token,
            f"publish-{lease.job_id}-{lease.token}",
        )
        async with github_client(token) as api:
            pull = await GitHubDelivery(api, repository.owner, repository.name).publish(
                branch=task.branch_name or "",
                base=str(native.checkpoint.get("base_branch") or repository.default_branch),
                title=task.title,
                body=f"Task: {task.external_key or task.id}\n\n{str(native.checkpoint.get('summary') or '')[-8000:]}\n\nDeterministic validation passed at `{validated}`. Review and current-SHA approval are required before merge.",
                owner=repository.owner,
                expected_sha=validated,
            )
        async with self.sessions.begin() as session:
            current = await session.get(Task, task.id, with_for_update=True)
            if current is None or current.lifecycle_version != lease.lifecycle_version:
                raise ValueError("Task changed during publication; inspect the task branch/PR")
            current.pull_request_number, current.pull_request_url = pull["number"], pull["html_url"]
        return Action.PUBLISHED

    async def _validate(
        self,
        client: httpx.AsyncClient,
        lease: PhaseLease,
        task: Task,
        native: DeveloperSession,
        team: Team,
    ) -> Action:
        commands = self.settings.v2_validation_commands.get(str(task.repository_id), [])
        if not commands or not task.branch_name:
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION,
                "Configure deterministic validation commands for this repository",
            )
        manifest = ValidationManifest(
            branch=task.branch_name,
            title=task.title,
            author_name=team.name,
            base_sha=str(native.checkpoint.get("base_sha") or ""),
            commands=commands,
            timeout_seconds=self.settings.developer_turn_timeout_seconds,
        )
        mounts = self._mounts(lease, native)
        atomic_json(mounts.manifest, manifest.model_dump(mode="json"))
        spec = validation_container_spec(mounts, image=self.settings.developer_container_image)
        spec["Labels"]["job_id"] = str(lease.job_id)
        validation_started = datetime.now(UTC)
        result = await run_container_job(
            client,
            f"validation-{lease.job_id}-{lease.token}",
            spec,
            self.settings.developer_turn_timeout_seconds,
        )
        async with self.sessions.begin() as session:
            current = await session.get(Task, task.id, with_for_update=True)
            state = await session.get(DeveloperSession, native.id, with_for_update=True)
            if (
                current is None
                or state is None
                or current.lifecycle_version != lease.lifecycle_version
            ):
                raise ValueError("Task changed while validating")
            passed = result.get("passed") is True
            for check in result["checks"]:
                session.add(
                    ValidationRun(
                        task_id=task.id,
                        head_sha=result["head_sha"],
                        requirement_version=task.requirement_version,
                        command=check["command"],
                        exit_code=check["exit_code"],
                        status="PASSED"
                        if check["exit_code"] == 0 and not check["timed_out"]
                        else "FAILED",
                        output_tail=check["output_tail"][-8000:],
                        started_at=datetime.fromisoformat(check["started_at"])
                        if check.get("started_at")
                        else validation_started,
                        finished_at=datetime.fromisoformat(check["finished_at"])
                        if check.get("finished_at")
                        else datetime.now(UTC),
                    )
                )
            current.current_revision = result["head_sha"]
            previous = current.progress_fingerprint or {}
            fingerprint = result["fingerprint"]
            current.no_progress_count = (
                current.no_progress_count + 1
                if not passed and previous.get("validation") == fingerprint
                else 0
            )
            current.progress_fingerprint = {"validation": fingerprint}
            if not passed:
                state.checkpoint = {
                    **state.checkpoint,
                    "next_feedback": "Fix these deterministic validation failures in this same session:\n"
                    + json.dumps(result["checks"])[-16000:],
                }
            stop_loop = current.no_progress_count >= 2
        if stop_loop:
            raise PhaseBlocked(
                WaitReason.MISSING_REQUIREMENT,
                "Repeated validation failure without workspace progress; inspect before another paid turn",
            )
        if passed:
            task.current_revision = result["head_sha"]
            review = await consult(
                self.sessions,
                self.settings,
                client,
                lease,
                task,
                native,
                "REVIEWER",
                change_context=str(result.get("change_context") or ""),
            )
            if review and review[0] == "REVIEW_CHANGES":
                await save_consultation_feedback(self.sessions, lease, native, *review)
                return Action.VALIDATION_FAILED
        return Action.VALIDATION_PASSED if passed else Action.VALIDATION_FAILED
