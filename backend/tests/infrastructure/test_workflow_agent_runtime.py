import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIAgent, Role, WorkflowNode
from app.domain.workflows import WorkflowNodeData
from app.infrastructure.persistence.agent_runtime import SqlAlchemyAgentRuntimeStore
from app.infrastructure.persistence.workflow_designer import (
    _normalized_node_state,
    _runtime_overrides,
    _validate_agent_runtime,
)


def node(**changes: object) -> WorkflowNodeData:
    values = {
        "id": str(uuid.uuid4()),
        "role": "REVIEWER",
        "label": "Eve",
        "position_x": 0,
        "position_y": 0,
        "provider": "anthropic",
        "model": "claude-opus-4-8",
    }
    values.update(changes)
    return WorkflowNodeData(**values)  # type: ignore[arg-type]


def records(item: WorkflowNodeData) -> tuple[AIAgent, Role]:
    role = Role(
        id=uuid.uuid4(),
        name="Reviewer",
        category="REVIEW",
        default_provider="anthropic",
        default_model="claude-opus-4-8",
        runtime_profile={},
        override_policy={"temperature": "ALLOW_IF_SUPPORTED"},
    )
    agent = AIAgent(
        id=uuid.uuid4(),
        team_id=uuid.uuid4(),
        role_id=role.id,
        name=item.label,
        provider=item.provider,
        model=item.model,
        runtime_overrides=_runtime_overrides(item),
    )
    return agent, role


def test_new_workflow_agent_receives_normalized_runtime_overrides() -> None:
    item = node(reasoning_effort="high", max_output_tokens=8_000, temperature=0.2)

    assert _runtime_overrides(item) == {
        "reasoning_level": "HIGH",
        "max_output_tokens": 8_000,
        "temperature": 0.2,
    }


def test_model_change_revalidates_existing_runtime_overrides() -> None:
    item = node(temperature=0.2)
    agent, role = records(item)

    with pytest.raises(ValueError, match="Agent Eve runtime is invalid.*temperature override"):
        _validate_agent_runtime(item, agent, role)


def test_disabled_or_unconfigured_agent_can_be_saved_for_later_setup() -> None:
    item = node(enabled=False, model="", temperature=0.2)
    agent, role = records(item)

    _validate_agent_runtime(item, agent, role)


def persisted_node(item: WorkflowNodeData) -> WorkflowNode:
    return cast(
        WorkflowNode,
        SimpleNamespace(
            integration_mode=item.integration_mode,
            poll_interval_seconds=item.poll_interval_seconds,
            filter_assignee_id=item.filter_assignee_id,
            filter_state_ids=list(item.filter_state_ids),
            integration_ids=list(item.integration_ids),
            integration_sync_status="READY",
            integration_sync_error=None,
            integration_last_synced_at=datetime.now(UTC),
            provider=item.provider,
            model=item.model,
            reasoning_effort=item.reasoning_effort,
            max_output_tokens=item.max_output_tokens,
            temperature=item.temperature,
            model_validation_status="VALID",
            model_validation_message="Model is available",
            model_validated_at=datetime.now(UTC),
        ),
    )


def test_model_change_invalidates_stale_validation_result() -> None:
    original = node(model="claude-old")
    changed = node(model="claude-new")

    normalized = _normalized_node_state(changed, persisted_node(original))

    assert normalized.model_validation_status == "NOT_CONFIGURED"
    assert normalized.model_validation_message is None
    assert normalized.model_validated_at is None


def test_unrelated_node_change_preserves_model_validation_result() -> None:
    original = node()
    changed = node(system_prompt="More review focus")
    current = persisted_node(original)

    normalized = _normalized_node_state(changed, current)

    assert normalized.model_validation_status == "VALID"
    assert normalized.model_validation_message == "Model is available"
    assert normalized.model_validated_at == current.model_validated_at


def test_effective_runtime_exposes_complete_configuration_provenance() -> None:
    item = node()
    agent, role = records(item)
    agent.config_version = 3
    role.version = 7
    store = SqlAlchemyAgentRuntimeStore(cast(AsyncSession, object()))

    view = store._view(agent, role)

    assert view["versions"] == {
        "role": 7,
        "agent": 3,
        "capabilities": "2026-09-06",
        "strategy": "v1",
    }
    assert view["effective_hash"]
