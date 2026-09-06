import hashlib
import json
import uuid
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, JobRole, WorkerRun
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
