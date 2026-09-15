import pytest

from app.intake.domain.eligibility import linear_eligible
from app.platform.integrations.application.configuration import merge_configuration


def test_editing_state_mapping_preserves_linear_intake_and_authority() -> None:
    current = {"assignee_id": "member", "source_state_ids": ["todo"], "actor_ids": ["owner"]}
    updated = merge_configuration("linear", current, {"done_state_id": "done"})
    assert linear_eligible(updated, "member", "todo")
    assert updated["actor_ids"] == ["owner"]
    assert (
        merge_configuration("linear", updated, {"source_state_ids": []})["source_state_ids"] == []
    )


@pytest.mark.parametrize("interval", [True, "60", 0, 14, 3601])
def test_invalid_polling_configuration_is_rejected(interval: object) -> None:
    with pytest.raises(ValueError, match="polling interval"):
        merge_configuration("trello", {}, {"poll_interval_seconds": interval})
