from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.models import AIRun, PricingCatalog
from app.delivery.infrastructure.status_sync import enqueue_status
from app.engineering.infrastructure.enrollment import enroll
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.platform.configuration.models import SettingsAuditEvent
from app.platform.configuration.settings import Settings
from app.teams.application.profiles import ProfileConflict
from app.teams.domain.automation import AutomationPolicy
from app.teams.infrastructure.automation import TeamAutomationPolicy, policy_payload, read_policy
from app.teams.infrastructure.statistics import statistics
from app.teams.infrastructure.team_models import Team


class SqlAutomationAdmin:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session, self.settings = session, settings

    async def retry_status_sync(self, task_id: UUID) -> None:
        task = await self.session.get(Task, task_id, with_for_update=True)
        if task is None:
            raise LookupError("Task not found")
        if task.archived_at:
            raise ProfileConflict("Status synchronization requires an unarchived V2 task")
        await enqueue_status(
            self.session, task.id, task.lifecycle_version, task.status or "", task.stage or ""
        )
        self.session.add(
            TaskEvent(
                task_id=task.id,
                source="user",
                event_type="V2_STATUS_SYNC_REQUESTED",
                payload={"actor": "local-operator"},
            )
        )
        await self.session.commit()

    async def reconcile_cost(self, run_id: UUID, amount: Decimal, reference: str) -> None:
        row = await self.session.get(AIRun, run_id, with_for_update=True)
        if row is None:
            raise LookupError("AI run not found")
        if (
            row.status == "RUNNING"
            or row.provider_cost_usd is not None
            or row.calculated_cost_usd is not None
        ):
            raise ProfileConflict(
                "Only stopped runs with unknown costs can be reconciled; known history is immutable"
            )
        evidence = {
            "amount_usd": str(amount),
            "reference": reference,
            "actor": "local-operator",
            "at": datetime.now(UTC).isoformat(),
        }
        row.calculated_cost_usd = amount
        row.raw_usage = {**(row.raw_usage or {}), "operator_cost_reconciliation": evidence}
        self.session.add(
            TaskEvent(
                task_id=row.task_id,
                source="user",
                event_type="V2_COST_RECONCILED",
                payload={"run_id": str(run_id), **evidence},
            )
        )
        await self.session.commit()

    async def statistics(self, team_id: UUID | None, days: int) -> dict[str, Any]:
        if team_id and not await self.session.get(Team, team_id):
            raise LookupError("Team not found")
        return await statistics(self.session, team_id, days)

    async def list_prices(self) -> list[dict[str, Any]]:
        rows = await self.session.scalars(
            select(PricingCatalog).order_by(PricingCatalog.effective_at.desc()).limit(200)
        )
        return [
            {column.name: getattr(row, column.name) for column in PricingCatalog.__table__.columns}
            for row in rows
        ]

    async def add_price(self, values: dict[str, Any]) -> UUID:
        row = PricingCatalog(**values)
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ProfileConflict(
                "Price version already exists; append a new version rather than rewrite historical costs"
            ) from exc
        return row.id

    async def read(self, team_id: UUID) -> tuple[AutomationPolicy, int]:
        if not await self.session.get(Team, team_id):
            raise LookupError("Team not found")
        row = await self.session.get(TeamAutomationPolicy, team_id)
        return await read_policy(self.session, team_id), row.version if row else 0

    async def save(self, team_id: UUID, policy: AutomationPolicy, version: int) -> int:
        team = await self.session.get(Team, team_id, with_for_update=True)
        if team is None:
            raise LookupError("Team not found")
        if any(str(repo) not in team.repository_ids for repo in policy.repository_ids):
            raise ValueError("Automation repositories must belong to the Team")
        row = await self.session.get(TeamAutomationPolicy, team_id, with_for_update=True)
        if (row.version if row else 0) != version:
            raise ProfileConflict("Automation policy changed; reload before saving")
        if row is None:
            row = TeamAutomationPolicy(team_id=team_id)
            self.session.add(row)
        old = dict(row.configuration or {})
        row.configuration, row.version = policy_payload(policy), version + 1
        self.session.add(
            SettingsAuditEvent(
                section="v2_automation",
                source="local-operator",
                old_values={"team_id": str(team_id), "version": version, "policy": old},
                new_values={
                    "team_id": str(team_id),
                    "version": version + 1,
                    "policy": row.configuration,
                },
            )
        )
        await self.session.commit()
        return version + 1

    async def enroll(self, task_id: UUID) -> None:
        task = await self.session.get(Task, task_id, with_for_update=True)
        if task is None:
            raise LookupError("Task not found")
        await enroll(self.session, task, self.settings, actor="operator")
        await self.session.commit()
