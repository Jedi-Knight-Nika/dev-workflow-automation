"""Explicit rollout and merge authority, independent of model instructions."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class AutomationPolicy:
    enrollment_enabled: bool = False
    auto_merge: bool = False
    repository_ids: tuple[UUID, ...] = ()
    authorized_reviewer_ids: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()
    task_budget_usd: Decimal = Decimal(2)
    team_budget_usd: Decimal = Decimal(20)
    require_formal_approval: bool = True
    reviewer_scope: Literal["allowlist", "any_human"] = "allowlist"

    def __post_init__(self) -> None:
        if (
            not self.task_budget_usd.is_finite()
            or not self.team_budget_usd.is_finite()
            or not (0 < self.task_budget_usd <= self.team_budget_usd <= 10000)
        ):
            raise ValueError("Budgets must be positive; task <= team <= 10000 USD")
        if self.enrollment_enabled and not self.repository_ids:
            raise ValueError("Enrollment requires explicitly allowed repositories")
        if self.reviewer_scope not in {"allowlist", "any_human"}:
            raise ValueError("Invalid reviewer scope")
        if self.auto_merge and (
            (self.reviewer_scope == "allowlist" and not self.authorized_reviewer_ids)
            or not self.required_checks
        ):
            raise ValueError("Auto-merge requires a reviewer policy and required CI check names")
        if len(set(self.repository_ids)) != len(self.repository_ids):
            raise ValueError("Duplicate repositories")
        if any(
            not value.isascii() or not value.isdecimal() or len(value) > 30
            for value in self.authorized_reviewer_ids
        ):
            raise ValueError("Use immutable numeric GitHub user IDs, not logins")
        if any(not value.strip() or len(value) > 200 for value in self.required_checks):
            raise ValueError("CI check names must contain 1–200 characters")
