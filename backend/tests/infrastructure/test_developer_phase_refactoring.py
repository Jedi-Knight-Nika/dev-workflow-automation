from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.handoffs import work_packet
from app.agent_runtime.domain.model_policy import ModelPolicy
from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.agent_codec import encode
from app.agent_runtime.infrastructure.models import DeveloperSession
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.infrastructure.developer_failures import block_failed_turn
from app.engineering.infrastructure.developer_request import build_developer_request
from app.engineering.infrastructure.executor import SqlPhaseExecutor
from app.engineering.infrastructure.phase_context import load_phase_context
from app.engineering.infrastructure.task_models import Task
from app.platform.configuration.settings import Settings
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


def request_context(checkpoint=None, *, resumed=False):
    task = Task(id=uuid4(), title="Preserve behavior", requirement_version=1, stage="DEVELOPING")
    native = DeveloperSession(
        id=uuid4(),
        task_id=task.id,
        checkpoint=checkpoint or {},
        native_session_id="session" if resumed else None,
    )
    return task, native


@pytest.mark.parametrize("routed_model,expected_queries", [("base", 1), ("alternate", 2)])
async def test_phase_pricing_is_loaded_once_per_model_per_phase(
    monkeypatch, routed_model, expected_queries
):
    policy = TokenEfficiencyPolicy(
        model_routes=tuple(
            ModelPolicy("openai", routed_model, role) for role in ("planning", "repair")
        )
    )
    task, native = request_context({"token_policy_override": asdict(policy)})
    task.team_id = uuid4()
    native.profile_id = uuid4()
    native.provider, native.model, native.harness = "openai", "base", "patch"
    profile = SimpleNamespace(provider="openai", model="base", harness="patch")
    rows = {Task: task, TeamAgentProfile: profile, Team: SimpleNamespace(id=task.team_id)}
    session = AsyncMock()
    session.get.side_effect = lambda model, identifier: rows.get(model)
    session.scalar.side_effect = [native, None, native, None]
    connection = AsyncMock()
    connection.__aenter__.return_value = session
    sessions = Mock(return_value=connection)
    price = SimpleNamespace(
        id=uuid4(),
        input_per_million=Decimal(1),
        output_per_million=Decimal(2),
        cached_input_per_million=Decimal("0.5"),
        cache_write_per_million=Decimal(0),
    )
    lookup = AsyncMock(return_value=price)
    monkeypatch.setattr("app.engineering.infrastructure.phase_context.standard_price", lookup)
    lease = PhaseLease(uuid4(), task.id, uuid4(), "DEVELOPER_TURN", 1)

    first = await load_phase_context(sessions, lease)
    assert lookup.await_count == expected_queries
    assert [model.policy.role for model in first.routed_models] == ["planning", "repair"]
    assert all(model.pricing_id == str(price.id) for model in first.routed_models)

    price.id = uuid4()
    second = await load_phase_context(sessions, lease)
    assert lookup.await_count == expected_queries * 2
    assert second.routed_models[0].pricing_id != first.routed_models[0].pricing_id


def test_fresh_and_resumed_requests_preserve_authority_and_supervision():
    task, native = request_context()
    prepared = build_developer_request(
        task, native, "Requirement", supervisor_guidance="\nGuidance"
    )
    assert prepared.request == prepared.prompt == "Requirement\nGuidance"
    assert prepared.feedback is None and prepared.work is not None
    assert prepared.work.payload["request"] == prepared.prompt
    native.native_session_id = "session"
    native.checkpoint = {"next_feedback": "  Fix current tests  "}
    prepared = build_developer_request(
        task, native, "Requirement", supervisor_guidance="\nGuidance"
    )
    assert prepared.request == "Requirement"
    assert prepared.feedback == prepared.prompt == "Fix current tests\nGuidance"


def test_resumed_request_requires_new_feedback_but_patch_resume_can_reuse_evidence():
    task, native = request_context(resumed=True)
    with pytest.raises(PhaseBlocked, match="needs new feedback"):
        build_developer_request(task, native, "Requirement")
    prepared = build_developer_request(task, native, "Requirement", patch_resume_allowed=True)
    assert prepared.feedback == "Requirement"


def test_repair_evidence_and_stale_checkpoint_guards_are_preserved():
    task, native = request_context({"repair_packet": {"failure": "current delta"}})
    task.stage = "FIXING"
    prepared = build_developer_request(task, native, "Requirement")
    assert prepared.prompt.startswith("Requirement\nCURRENT REPAIR EVIDENCE")
    assert "current delta" in prepared.prompt
    native.checkpoint = {"rollover_checkpoint": {"requirement_version": 2}}
    with pytest.raises(PhaseBlocked, match="Checkpoint requirement version changed"):
        build_developer_request(task, native, "Requirement")


def test_coordinator_delta_retains_invariants_and_rejects_stale_handoffs():
    import json

    task, native = request_context()
    packet = work_packet(task.id, 1, None, "Authorized delta", invariants=("Keep the API",))
    native.checkpoint = {"coordinator_guidance": json.loads(encode(packet, "JSON_VERBOSE"))}
    prepared = build_developer_request(task, native, "Requirement")
    assert "Authorized delta" in prepared.prompt and "Keep the API" in prepared.prompt
    task.requirement_version = 2
    with pytest.raises(PhaseBlocked, match="Coordinator handoff is stale"):
        build_developer_request(task, native, "Requirement")


@pytest.mark.parametrize("mode", ["compaction", "continuity"])
def test_non_development_requests_do_not_create_work_packets(mode):
    task, native = request_context({"rollover_digest": "verified"})
    prepared = build_developer_request(task, native, "Requirement", **{mode: True})
    assert prepared.work is None
    if mode == "continuity":
        assert "exactly ACK verified" in prepared.prompt


@pytest.mark.parametrize(
    "code,harness,reason",
    [
        ("TURN_INPUT_LIMIT", "patch", WaitReason.TOKEN_LIMIT),
        ("SUPERVISOR_STOP", "codex", WaitReason.RUNTIME_FAILURE),
        ("REPEATED_READ_LOOP", "codex", WaitReason.NO_PROGRESS),
        ("TURN_BUDGET_EXHAUSTED", "codex", WaitReason.BUDGET_EXHAUSTED),
        ("PATCH_LIMIT", "patch", WaitReason.NO_PROGRESS),
        ("BUDGET_LIMIT", "patch", WaitReason.BUDGET_EXHAUSTED),
        ("PROVIDER_AUTHENTICATION_FAILED", "codex", WaitReason.MISSING_CONFIGURATION),
        (None, "codex", WaitReason.MISSING_REQUIREMENT),
    ],
)
def test_failure_classification_keeps_existing_precedence(code, harness, reason):
    receipt = TurnReceipt(
        "session", "turn", "Preserved evidence", "failed", Usage(), failure_code=code
    )
    with pytest.raises(PhaseBlocked) as failure:
        block_failed_turn(receipt, harness)
    assert failure.value.reason == reason


@pytest.mark.asyncio
async def test_merge_dispatch_does_not_load_a_native_context(monkeypatch):
    merge = AsyncMock(return_value=Action.MERGED)
    load = AsyncMock()
    monkeypatch.setattr("app.engineering.infrastructure.executor.merge_phase", merge)
    monkeypatch.setattr("app.engineering.infrastructure.executor.load_phase_context", load)
    sessions = AsyncMock()
    lease = PhaseLease(uuid4(), uuid4(), uuid4(), "MERGE_PR", 1)
    executor = SqlPhaseExecutor(sessions, Settings())
    assert await executor.execute(lease) == Action.MERGED
    merge.assert_awaited_once_with(sessions, lease)
    load.assert_not_called()
