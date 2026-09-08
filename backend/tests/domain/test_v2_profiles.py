from dataclasses import replace
from decimal import Decimal

import pytest

from app.teams.domain.profiles import RoleKind, default_profiles


def test_exactly_four_fixed_roles_with_optional_helpers() -> None:
    profiles = default_profiles()
    assert [profile.role_kind for profile in profiles] == list(RoleKind)
    assert [profile.enabled for profile in profiles] == [True, True, False, False]
    assert profiles[1].model == "gpt-5.6-terra"


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": False},
        {"display_name": "  "},
        {"model": ""},
        {"provider": "anthropic", "harness": "codex"},
        {"effort": "ultra"},
        {"supplemental_instructions": "x" * 8001},
        {"soft_budget_usd": Decimal(10), "hard_budget_usd": Decimal(5)},
    ],
)
def test_profile_rejects_invalid_or_unsupported_contract(changes: dict) -> None:
    with pytest.raises(ValueError):
        replace(default_profiles()[1], **changes)
