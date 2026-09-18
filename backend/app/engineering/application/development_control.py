"""Development continuation and receipt policy, independent of SQL, Docker and Git."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.handoffs import WorkOutcome
from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.engineering.application.developer_failures import block_failed_turn
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.application.ports.development_recovery import (
    DevelopmentRecovery,
    ResumablePhaseExecutor,
)
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.domain.repair_limits import REPAIR_INPUT_TOKENS


@dataclass(frozen=True)
class DevelopmentSession:
    session_id: UUID
    requirement_version: int
    native_session_id: str | None
    harness: str
    checkpoint: Mapping[str, Any]


def bounded_repair_policy(policy: TokenEfficiencyPolicy) -> TokenEfficiencyPolicy:
    return replace(
        policy,
        mode="ENFORCE",
        reasoning_effort="low",
        first_edit_warning_tokens=20000,
        exploration_hard_tokens=50000,
        no_progress_tokens=20000,
        max_turn_input_tokens=REPAIR_INPUT_TOKENS,
        automatic_rollover=False,
    )


class DevelopmentControl:
    def __init__(
        self, recovery: DevelopmentRecovery, *, compact_before_feedback_tokens: int = 0
    ) -> None:
        self.recovery = recovery
        self.compact_before_feedback_tokens = compact_before_feedback_tokens

    async def recover_candidate(
        self, lease: PhaseLease, session_id: UUID, *, allow_repair: bool
    ) -> Action | None:
        if await self.recovery.validate_candidate(lease, session_id):
            return Action.VALIDATE_CANDIDATE
        if allow_repair and await self.recovery.repair(lease, session_id):
            return Action.BOUNDED_REPAIR
        return None

    async def continue_session(
        self,
        lease: PhaseLease,
        state: DevelopmentSession,
        phases: ResumablePhaseExecutor,
        token_policy: TokenEfficiencyPolicy,
        *,
        compaction: bool,
        compacted: bool,
        continuity: bool,
    ) -> Action | None:
        checkpoint_digest = state.checkpoint.get("rollover_digest")
        if (
            checkpoint_digest
            and state.checkpoint.get("continuity_acknowledged") != checkpoint_digest
            and not continuity
        ):
            if state.native_session_id:
                raise PhaseBlocked(
                    WaitReason.MISSING_REQUIREMENT,
                    "Checkpoint acknowledgement failed; no automatic paid retry",
                )
            await phases.execute(lease, continuity=True)
            return await phases.execute(lease)
        threshold = self.compact_before_feedback_tokens
        active_context = (state.checkpoint.get("token_efficiency") or {}).get(
            "active_context_estimate"
        )
        if (
            not compaction
            and not continuity
            and state.native_session_id
            and state.checkpoint.get("next_feedback")
            and token_policy.automatic_rollover
            and state.harness not in {"responses", "patch"}
            and token_policy.mode == "ENFORCE"
            and active_context is not None
            and active_context >= token_policy.active_context_soft_tokens
        ):
            try:
                await self.recovery.rollover(
                    lease,
                    state.requirement_version,
                    str(
                        state.checkpoint.get("summary")
                        or "Continue from current validated code and pending review feedback."
                    )[:1800],
                )
            except (ValueError, RuntimeError, OSError) as exc:
                raise PhaseBlocked(
                    WaitReason.MISSING_REQUIREMENT,
                    "CHECKPOINT_PERSISTENCE_FAILED; retained native context",
                ) from exc
            return await phases.execute(lease)
        if (
            not compaction
            and not compacted
            and threshold
            and state.harness not in {"responses", "patch"}
            and state.native_session_id
            and active_context is not None
            and active_context >= threshold
            and int(state.checkpoint.get("compaction_count", 0)) < token_policy.max_compactions
            and state.checkpoint.get("next_feedback")
        ):
            # Two separately metered runs, one native session. The next
            # call reloads usage and cannot reuse the compaction reserve.
            await phases.execute(lease, compaction=True)
            return await phases.execute(lease, compacted=True)
        return None

    async def finish(
        self,
        lease: PhaseLease,
        state: DevelopmentSession,
        phases: ResumablePhaseExecutor,
        token_policy: TokenEfficiencyPolicy,
        receipt: TurnReceipt,
    ) -> Action:
        if receipt.status != "completed":
            if (
                receipt.failure_code == "TURN_INPUT_LIMIT"
                and await self.recovery.validate_candidate(lease, state.session_id)
            ):
                return Action.VALIDATE_CANDIDATE
            if receipt.failure_code == "TURN_INPUT_LIMIT" and await self.recovery.repair(
                lease, state.session_id
            ):
                return Action.BOUNDED_REPAIR
            block_failed_turn(receipt, state.harness)
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
                await self.recovery.rollover(
                    lease,
                    state.requirement_version,
                    receipt.summary[len("MILESTONE_COMPLETE\n") :][:1800],
                )
            except (ValueError, RuntimeError, OSError) as exc:
                raise PhaseBlocked(
                    WaitReason.MISSING_REQUIREMENT,
                    "Milestone checkpoint blocked; retained native context",
                ) from exc
            return await phases.execute(lease)
        if (
            outcome == WorkOutcome.NEEDS_PLAN
            or outcome is None
            and receipt.summary.strip().split("\n", 1)[0].strip() == "NEEDS_PLAN"
        ):
            return Action.NEEDS_PLAN
        return Action.IMPLEMENTED
