import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.envelope import AgentEnvelope
from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.domain.usage import Usage
from app.engineering.application.development_control import (
    DevelopmentControl,
    DevelopmentSession,
    bounded_repair_policy,
)
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import Action, WaitReason


@pytest.fixture
def control():
    return DevelopmentControl(
        AsyncMock(
            validate_candidate=AsyncMock(return_value=False), repair=AsyncMock(return_value=False)
        ),
        compact_before_feedback_tokens=50000,
    )


@pytest.fixture
def phases():
    return AsyncMock(execute=AsyncMock(return_value=Action.IMPLEMENTED))


@pytest.fixture
def lease():
    return PhaseLease(uuid4(), uuid4(), uuid4(), "DEVELOPER_TURN", 1)


def session(**changes):
    return replace(DevelopmentSession(uuid4(), 1, "native-session", "codex", {}), **changes)


def receipt(**changes):
    return replace(TurnReceipt("native-session", "turn", "Done", "completed", Usage()), **changes)


async def continue_session(control, phases, lease, state, policy=None, **flags):
    return await control.continue_session(
        lease,
        state,
        phases,
        policy or TokenEfficiencyPolicy(),
        **({"compaction": False, "compacted": False, "continuity": False} | flags),
    )


async def test_candidate_validation_precedes_another_paid_repair(control, lease):
    control.recovery.validate_candidate.return_value = True
    assert (
        await control.recover_candidate(lease, uuid4(), allow_repair=True)
        == Action.VALIDATE_CANDIDATE
    )
    control.recovery.repair.assert_not_awaited()


@pytest.mark.parametrize("allow_repair", [False, True])
async def test_repair_requires_explicit_admission_path(control, lease, allow_repair):
    control.recovery.repair.return_value = True
    expected = Action.BOUNDED_REPAIR if allow_repair else None
    assert await control.recover_candidate(lease, uuid4(), allow_repair=allow_repair) == expected
    assert control.recovery.repair.await_count == int(allow_repair)


def test_bounded_repair_preserves_policy_without_mutating_it():
    original = TokenEfficiencyPolicy(automatic_rollover=True)
    policy = bounded_repair_policy(original)
    assert original.automatic_rollover and original.mode == "INSTRUMENT"
    assert policy.mode == "ENFORCE" and policy.reasoning_effort == "low"
    assert not policy.automatic_rollover and policy.max_turn_input_tokens == 80000
    assert policy.active_context_soft_tokens == original.active_context_soft_tokens


async def test_unacknowledged_checkpoint_runs_continuity_then_reloads_context(
    control, phases, lease
):
    state = session(native_session_id=None, checkpoint={"rollover_digest": "checkpoint"})
    assert await continue_session(control, phases, lease, state) == Action.IMPLEMENTED
    assert [call.kwargs for call in phases.execute.await_args_list] == [{"continuity": True}, {}]
    assert all(call.args == (lease,) for call in phases.execute.await_args_list)
    control.recovery.rollover.assert_not_awaited()


async def test_failed_checkpoint_acknowledgement_never_retries_paid_session(control, phases, lease):
    state = session(checkpoint={"rollover_digest": "checkpoint"})
    with pytest.raises(PhaseBlocked, match="no automatic paid retry"):
        await continue_session(control, phases, lease, state)
    phases.execute.assert_not_awaited()


@pytest.mark.parametrize("continuity", [False, True])
async def test_acknowledged_checkpoint_or_active_continuity_does_not_repeat(
    control, phases, lease, continuity
):
    state = session(
        checkpoint={"rollover_digest": "checkpoint", "continuity_acknowledged": "checkpoint"}
    )
    assert await continue_session(control, phases, lease, state, continuity=continuity) is None
    phases.execute.assert_not_awaited()


async def test_rollover_is_saved_before_reexecution_and_takes_precedence(control, phases, lease):
    state = session(
        checkpoint={
            "next_feedback": "Fix it",
            "summary": "Bounded evidence",
            "token_efficiency": {"active_context_estimate": 120000},
        }
    )
    order = []
    control.recovery.rollover.side_effect = lambda *_: order.append("save")
    phases.execute.side_effect = lambda *_args, **_kwargs: (
        order.append("execute") or Action.IMPLEMENTED
    )
    policy = TokenEfficiencyPolicy(mode="ENFORCE", automatic_rollover=True)
    assert await continue_session(control, phases, lease, state, policy) == Action.IMPLEMENTED
    assert order == ["save", "execute"]
    control.recovery.rollover.assert_awaited_once_with(lease, 1, "Bounded evidence")
    phases.execute.assert_awaited_once_with(lease)


@pytest.mark.parametrize("error", [ValueError, RuntimeError, OSError])
async def test_checkpoint_failure_prevents_another_turn(control, phases, lease, error):
    state = session(
        checkpoint={
            "next_feedback": "Fix it",
            "token_efficiency": {"active_context_estimate": 120000},
        }
    )
    control.recovery.rollover.side_effect = error("storage unavailable")
    with pytest.raises(PhaseBlocked, match="CHECKPOINT_PERSISTENCE_FAILED"):
        await continue_session(
            control,
            phases,
            lease,
            state,
            TokenEfficiencyPolicy(mode="ENFORCE", automatic_rollover=True),
        )
    phases.execute.assert_not_awaited()


async def test_compaction_is_a_separate_turn_followed_by_a_fresh_admission(control, phases, lease):
    state = session(
        checkpoint={
            "next_feedback": "Fix it",
            "token_efficiency": {"active_context_estimate": 50000},
        }
    )
    assert await continue_session(control, phases, lease, state) == Action.IMPLEMENTED
    assert [call.kwargs for call in phases.execute.await_args_list] == [
        {"compaction": True},
        {"compacted": True},
    ]
    control.recovery.rollover.assert_not_awaited()


@pytest.mark.parametrize("harness", ["patch", "responses"])
async def test_fresh_request_harnesses_never_compact_or_rollover(control, phases, lease, harness):
    state = session(
        harness=harness,
        checkpoint={
            "next_feedback": "Fix it",
            "token_efficiency": {"active_context_estimate": 200000},
        },
    )
    assert (
        await continue_session(
            control,
            phases,
            lease,
            state,
            TokenEfficiencyPolicy(mode="ENFORCE", automatic_rollover=True),
        )
        is None
    )
    phases.execute.assert_not_awaited()
    control.recovery.rollover.assert_not_awaited()


@pytest.mark.parametrize("flags", [{"compaction": True}, {"compacted": True}])
async def test_compaction_cannot_repeat_within_the_same_continuation(control, phases, lease, flags):
    state = session(
        checkpoint={
            "next_feedback": "Fix it",
            "token_efficiency": {"active_context_estimate": 50000},
        }
    )
    assert await continue_session(control, phases, lease, state, **flags) is None
    phases.execute.assert_not_awaited()


async def test_exhausted_compaction_limit_does_not_create_another_turn(control, phases, lease):
    state = session(
        checkpoint={
            "next_feedback": "Fix it",
            "compaction_count": 2,
            "token_efficiency": {"active_context_estimate": 50000},
        }
    )
    assert await continue_session(control, phases, lease, state) is None
    phases.execute.assert_not_awaited()


async def test_compaction_cancellation_does_not_start_followup_turn(control, phases, lease):
    state = session(
        checkpoint={
            "next_feedback": "Fix it",
            "token_efficiency": {"active_context_estimate": 50000},
        }
    )
    phases.execute.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await continue_session(control, phases, lease, state)
    phases.execute.assert_awaited_once_with(lease, compaction=True)


@pytest.mark.parametrize("candidate", [True, False])
async def test_input_limit_recovers_candidate_before_paid_repair(control, phases, lease, candidate):
    state = session()
    control.recovery.validate_candidate.return_value = candidate
    control.recovery.repair.return_value = True
    result = await control.finish(
        lease,
        state,
        phases,
        TokenEfficiencyPolicy(),
        receipt(status="failed", failure_code="TURN_INPUT_LIMIT"),
    )
    assert result == (Action.VALIDATE_CANDIDATE if candidate else Action.BOUNDED_REPAIR)
    assert control.recovery.repair.await_count == int(not candidate)
    phases.execute.assert_not_awaited()


async def test_failed_receipt_cannot_be_overridden_by_successful_summary(control, phases, lease):
    with pytest.raises(PhaseBlocked) as failure:
        await control.finish(
            lease,
            session(),
            phases,
            TokenEfficiencyPolicy(),
            receipt(status="failed", failure_code="NO_PROGRESS", summary="Done"),
        )
    assert failure.value.reason == WaitReason.NO_PROGRESS
    phases.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "summary,expected", [("Done", Action.IMPLEMENTED), ("NEEDS_PLAN\nEvidence", Action.NEEDS_PLAN)]
)
async def test_legacy_completed_receipts_keep_their_meaning(
    control, phases, lease, summary, expected
):
    assert (
        await control.finish(
            lease, session(), phases, TokenEfficiencyPolicy(), receipt(summary=summary)
        )
        == expected
    )
    control.recovery.validate_candidate.assert_not_awaited()


async def test_structured_receipt_takes_precedence_over_legacy_prose(control, phases, lease):
    result = AgentEnvelope(1, "result", lease.task_id, 1, None, {"outcome": "IMPLEMENTED"})
    assert (
        await control.finish(
            lease,
            session(),
            phases,
            TokenEfficiencyPolicy(),
            receipt(summary="NEEDS_PLAN", result=result),
        )
        == Action.IMPLEMENTED
    )


@pytest.mark.parametrize(
    "outcome,reason",
    [("NEEDS_HUMAN", WaitReason.MISSING_REQUIREMENT), ("FAILED", WaitReason.RUNTIME_FAILURE)],
)
async def test_structured_stops_remain_stopped(control, phases, lease, outcome, reason):
    result = AgentEnvelope(1, "result", lease.task_id, 1, None, {"outcome": outcome})
    with pytest.raises(PhaseBlocked) as failure:
        await control.finish(
            lease, session(), phases, TokenEfficiencyPolicy(), receipt(result=result)
        )
    assert failure.value.reason == reason
    phases.execute.assert_not_awaited()


async def test_milestone_requires_explicit_rollover_policy(control, phases, lease):
    with pytest.raises(PhaseBlocked, match="approve a checkpoint"):
        await control.finish(
            lease,
            session(),
            phases,
            TokenEfficiencyPolicy(),
            receipt(summary="MILESTONE_COMPLETE\nEvidence"),
        )
    control.recovery.rollover.assert_not_awaited()
    phases.execute.assert_not_awaited()


async def test_milestone_persists_checkpoint_before_new_admission(control, phases, lease):
    policy = TokenEfficiencyPolicy(mode="ENFORCE", automatic_rollover=True)
    assert (
        await control.finish(
            lease, session(), phases, policy, receipt(summary="MILESTONE_COMPLETE\nEvidence")
        )
        == Action.IMPLEMENTED
    )
    control.recovery.rollover.assert_awaited_once_with(lease, 1, "Evidence")
    phases.execute.assert_awaited_once_with(lease)
