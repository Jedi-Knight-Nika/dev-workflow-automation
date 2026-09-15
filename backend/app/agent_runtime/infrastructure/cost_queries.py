"""Shared SQL expressions for receipts; missing cost stays unknown, never zero."""

from decimal import Decimal

from sqlalchemy import and_, case, func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.agent_runtime.infrastructure.models import AIRun


def settled_cost() -> ColumnElement[Decimal]:
    return func.coalesce(AIRun.provider_cost_usd, AIRun.calculated_cost_usd)


def budget_cost() -> ColumnElement[Decimal]:
    """Admission includes every running reservation until its receipt settles."""
    return case((AIRun.status == "RUNNING", AIRun.reserved_cost_usd), else_=settled_cost())


def engineering_cost() -> ColumnElement[Decimal]:
    """Coding can overlap a reserved Coordinator request, within the shared budget."""
    coordinator = and_(AIRun.status == "RUNNING", AIRun.role_kind == "COORDINATOR")
    return case((coordinator, AIRun.reserved_cost_usd), else_=settled_cost())


def unsettled_usage() -> ColumnElement[bool]:
    return or_(AIRun.status == "RUNNING", settled_cost().is_(None))


def unsettled_engineering_usage() -> ColumnElement[bool]:
    return or_(
        and_(AIRun.status == "RUNNING", AIRun.role_kind != "COORDINATOR"),
        engineering_cost().is_(None),
    )
