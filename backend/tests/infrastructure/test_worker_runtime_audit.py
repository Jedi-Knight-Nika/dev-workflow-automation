import hashlib
import json
import uuid
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIAgent, Job, JobRole, Role, WorkerRun
from app.domain.workflows import WorkflowNodeData
from app.infrastructure.persistence.agent_runtime import resolve_agent_runtime_config
from app.infrastructure.persistence.workflow_designer import _runtime_overrides
from app.infrastructure.workers.structured_output import ProviderAttempt
from app.providers import ProviderResponse
from app.worker import ResolvedAgentConfig, RuntimeAuditSnapshot, persist_attempts


class RecordingSession:
    def __init__(self) -> None:
        self.records: list[object] = []
        self.commits = 0

    def add(self, record: object) -> None:
        self.records.append(record)

    async def commit(self) -> None:
        self.commits += 1


def resolved_config(runtime: dict[str, object]) -> ResolvedAgentConfig:
    fingerprint = hashlib.sha256(
        json.dumps(runtime, sort_keys=True, default=str).encode()
    ).hexdigest()
    return ResolvedAgentConfig(
        provider="anthropic",
        model="claude-test",
        system_prompt="review",
        configuration={},
        repository_ids=(),
        permissions=("READ_REPOSITORY",),
        knowledge_scope=("TASK_MEMORY",),
        effective_runtime=runtime,
        effective_runtime_hash=fingerprint,
        model_capability_version="cap-1",
        agent_config_version=3,
        strategy_version="strategy-1",
    )


def test_runtime_audit_snapshot_is_detached_from_resolved_configuration() -> None:
    runtime: dict[str, object] = {"reasoning_level": "HIGH", "limits": {"tools": 40}}
    snapshot = RuntimeAuditSnapshot.capture(resolved_config(runtime))

    cast(dict[str, int], runtime["limits"])["tools"] = 1

    assert snapshot.effective_runtime()["limits"] == {"tools": 40}


def test_runtime_audit_snapshot_rejects_changed_configuration() -> None:
    config = resolved_config({"reasoning_level": "HIGH"})
    assert config.effective_runtime is not None
    config.effective_runtime["reasoning_level"] = "LOW"

    with pytest.raises(RuntimeError, match="changed after resolution"):
        RuntimeAuditSnapshot.capture(config)


@pytest.mark.asyncio
async def test_worker_runs_receive_independent_runtime_snapshots() -> None:
    runtime: dict[str, object] = {"reasoning_level": "HIGH", "limits": {"tools": 40}}
    snapshot = RuntimeAuditSnapshot.capture(resolved_config(runtime))
    session = RecordingSession()
    job = Job(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        role=JobRole.REVIEWER,
        action="REVIEW_IMPLEMENTATION",
    )
    attempts = [
        ProviderAttempt(ProviderResponse("{}", input_tokens=10, output_tokens=2), 100),
        ProviderAttempt(ProviderResponse("{}", input_tokens=12, output_tokens=3), 120),
    ]

    await persist_attempts(
        cast(AsyncSession, session),
        job,
        "anthropic",
        "claude-test",
        attempts,
        {},
        snapshot,
    )

    first, second = (cast(WorkerRun, record) for record in session.records)
    cast(dict[str, int], first.effective_runtime_config["limits"])["tools"] = 1
    assert second.effective_runtime_config["limits"] == {"tools": 40}
    assert session.commits == 1


@pytest.mark.asyncio
async def test_role_and_workflow_configuration_becomes_immutable_worker_audit() -> None:
    role = Role(
        id=uuid.uuid4(),
        name="Reviewer",
        category="REVIEW",
        default_provider="anthropic",
        default_model="claude-opus-4-8",
        runtime_profile={
            "reasoning_default": "HIGH",
            "reasoning_min": "LOW",
            "reasoning_max": "HIGH",
            "context_strategy": "DEEP",
            "max_tool_calls": 40,
        },
        override_policy={
            "reasoning_level": "ALLOW_WITHIN_RANGE",
            "max_output_tokens": "ALLOW",
        },
        version=5,
    )
    node = WorkflowNodeData(
        id=str(uuid.uuid4()),
        role="REVIEWER",
        label="Eve",
        position_x=0,
        position_y=0,
        provider="anthropic",
        model="claude-opus-4-8",
        reasoning_effort="medium",
        max_output_tokens=8_000,
    )
    agent = AIAgent(
        id=uuid.uuid4(),
        team_id=uuid.uuid4(),
        role_id=role.id,
        name="Eve",
        provider=node.provider,
        model=node.model,
        runtime_overrides=_runtime_overrides(node),
        config_version=3,
    )
    runtime = resolve_agent_runtime_config(agent, role)
    resolved = ResolvedAgentConfig(
        provider=runtime.provider,
        model=runtime.model,
        system_prompt="review",
        configuration={},
        repository_ids=(),
        role_id=role.id,
        role_version=role.version,
        agent_id=agent.id,
        permissions=("READ_REPOSITORY", "RUN_TESTS"),
        knowledge_scope=("TASK_MEMORY",),
        effective_runtime=runtime.snapshot(),
        effective_runtime_hash=runtime.fingerprint(),
        model_capability_version=runtime.capability_version,
        agent_config_version=agent.config_version,
        strategy_version=runtime.strategy_version,
    )
    audit = RuntimeAuditSnapshot.capture(resolved)
    session = RecordingSession()
    job = Job(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        role=JobRole.REVIEWER,
        action="REVIEW_IMPLEMENTATION",
    )

    await persist_attempts(
        cast(AsyncSession, session),
        job,
        runtime.provider,
        runtime.model,
        [ProviderAttempt(ProviderResponse("{}", input_tokens=20, output_tokens=4), 100)],
        {},
        audit,
    )
    role.runtime_profile["context_strategy"] = "MINIMAL"
    agent.runtime_overrides["reasoning_level"] = "LOW"

    worker_run = cast(WorkerRun, session.records[0])
    assert worker_run.effective_runtime_config["reasoning_level"] == "MEDIUM"
    assert worker_run.effective_runtime_config["context_strategy"] == "DEEP"
    assert worker_run.effective_runtime_config["max_output_tokens"] == 8_000
    assert worker_run.role_version == 5
    assert worker_run.agent_config_version == 3
    assert worker_run.model_capability_version == runtime.capability_version
    assert worker_run.effective_runtime_config_hash == runtime.fingerprint()
