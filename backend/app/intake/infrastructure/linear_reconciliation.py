from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engineering.infrastructure.job_queue import record_event, request_execution
from app.engineering.infrastructure.task_models import Task
from app.intake.application.ports.task_reconciliation import ReconciliationResult
from app.intake.domain.linear import configured_repository_id, linear_datetime, linear_priority
from app.intake.infrastructure.linear_client import LinearClient, LinearIssue
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.teams.infrastructure.routing import assign_routed_team


class SqlAlchemyLinearTaskReconciliation:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def reconcile_due(self) -> ReconciliationResult:
        async with self._session_factory() as session:
            return await self._reconcile_fixed(session, datetime.now(UTC))

    async def _reconcile_fixed(self, session: AsyncSession, now: datetime) -> ReconciliationResult:
        """V2 polls configured source IDs, never a removed workflow node."""
        integration = await session.scalar(
            select(Integration)
            .where(Integration.provider_name == "linear")
            .with_for_update(skip_locked=True)
        )
        if integration is None or not integration.encrypted_credentials:
            return ReconciliationResult(processed=False)
        config = integration.configuration or {}
        assignee = config.get("v2_assignee_id")
        states = config.get("v2_source_state_ids")
        if (
            not isinstance(assignee, str)
            or not assignee
            or (not isinstance(states, list))
            or (not states)
        ):
            return ReconciliationResult(processed=False)
        if any(not isinstance(value, str) or not value for value in states):
            return ReconciliationResult(processed=False)
        if integration.last_synced_at and integration.last_synced_at + timedelta(seconds=60) > now:
            return ReconciliationResult(processed=False)
        integration.last_synced_at = now
        imported = updated = 0
        try:
            async with session.begin_nested():
                issues = await LinearClient(
                    cipher.decrypt(integration.encrypted_credentials)
                ).list_issues(assignee, states)
                for issue in issues:
                    created = await self._upsert_issue(session, integration, issue)
                    imported += int(created)
                    updated += int(not created)
            integration.sync_status, integration.last_error = ("READY", None)
        except Exception as exc:  # noqa: BLE001 -- durable integration boundary; preserve other providers
            integration.sync_status, integration.last_error = (
                "FAILED",
                f"V2 Linear poll failed: {type(exc).__name__}",
            )
            imported = updated = 0
        await session.commit()
        return ReconciliationResult(processed=True, imported=imported, updated=updated)

    async def _upsert_issue(
        self, session: AsyncSession, integration: Integration, issue: LinearIssue
    ) -> bool:
        task = await session.scalar(select(Task).where(Task.external_key == issue["identifier"]))
        created = task is None
        if task is None:
            task = Task(
                external_key=issue["identifier"],
                title=issue["title"],
                description=issue["description"],
                priority=linear_priority(issue["priority"]),
                repository_id=configured_repository_id(integration.configuration),
            )
            session.add(task)
            await session.flush()
            await assign_routed_team(session, task, reason="linear-reconciliation")
            await request_execution(session, task, actor="tracker:ingestion")
            await record_event(
                session,
                task.id,
                "TASK_CREATED_FROM_LINEAR_RECONCILIATION",
                {"linear_issue_id": issue["id"], "identifier": issue["identifier"]},
                source="linear",
            )
        else:
            from app.intake.infrastructure.v2_events import requirements_changed

            await requirements_changed(
                session, task, issue["title"], issue["description"], source="linear"
            )
            task.title = issue["title"]
            task.description = issue["description"]
            task.priority = linear_priority(issue["priority"])
        task.due_at = linear_datetime(issue["raw"].get("dueDate"))
        snapshot = await session.scalar(
            select(ExternalTaskSnapshot).where(
                ExternalTaskSnapshot.provider == "linear",
                ExternalTaskSnapshot.external_id == issue["id"],
            )
        )
        if snapshot is None:
            snapshot = ExternalTaskSnapshot(
                task_id=task.id,
                provider="linear",
                external_id=issue["id"],
                identifier=issue["identifier"],
            )
            session.add(snapshot)
        snapshot.task_id = task.id
        snapshot.assignee_id = issue["assignee_id"]
        snapshot.state_id = issue["state_id"]
        snapshot.raw_payload = issue["raw"]
        snapshot.synchronized_at = datetime.now(UTC)
        return created
