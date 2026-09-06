import uuid

import pytest

from app.db.models import AIAgent, Role
from app.domain.workflows import WorkflowNodeData
from app.infrastructure.persistence.workflow_designer import (
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
