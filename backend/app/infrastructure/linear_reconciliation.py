from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.task_reconciliation import ReconciliationResult
from app.config import get_settings
from app.db.models import ExternalTaskSnapshot, Integration, JobRole, Task, WorkflowNode
from app.domain.webhooks import configured_repository_id, linear_datetime, linear_priority
from app.infrastructure.persistence.job_operations import enqueue_job, record_event
from app.infrastructure.persistence.team_routing import assign_routed_team
from app.infrastructure.security.crypto import cipher
from app.integrations.linear import LinearClient, LinearIssue


class SqlAlchemyLinearTaskReconciliation:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def reconcile_due(self) -> ReconciliationResult:
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            if get_settings().new_fixed_lifecycle and not get_settings().legacy_workflow_routing:
                return await self._reconcile_fixed(session, now)
            node = await session.scalar(
                select(WorkflowNode)
                .where(
                    WorkflowNode.role == "DELIVERER",
                    WorkflowNode.enabled.is_(True),
                    WorkflowNode.integration_mode.in_(["poll", "hybrid"]),
                    WorkflowNode.filter_assignee_id != "",
                )
                .order_by(WorkflowNode.integration_last_synced_at.asc().nullsfirst())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if node is None or (
                node.integration_last_synced_at is not None
                and node.integration_last_synced_at + timedelta(seconds=node.poll_interval_seconds)
                > now
            ):
                return ReconciliationResult(processed=False)
            node.integration_sync_status = "RUNNING"
            node.integration_sync_error = None
            try:
                integration = await self._linear_integration(session, node)
                integration.sync_status = "RUNNING"
                issues = await LinearClient(
                    cipher.decrypt(integration.encrypted_credentials or b"")
                ).list_issues(node.filter_assignee_id, list(node.filter_state_ids or []))
                imported = 0
                updated = 0
                for issue in issues:
                    created = await self._upsert_issue(session, integration, issue)
                    imported += int(created)
                    updated += int(not created)
                node.integration_sync_status = "READY"
                node.integration_last_synced_at = now
                integration.sync_status = "READY"
                integration.last_synced_at = now
                integration.last_error = None
                await session.commit()
                return ReconciliationResult(processed=True, imported=imported, updated=updated)
            except Exception as exc:  # noqa: BLE001 - persist third-party failures for operators
                node.integration_sync_status = "FAILED"
                node.integration_sync_error = str(exc)[:1000]
                node.integration_last_synced_at = now
                failed_integration = await self._session_integration(session)
                if failed_integration is not None:
                    failed_integration.sync_status = "FAILED"
                    failed_integration.last_synced_at = now
                    failed_integration.last_error = str(exc)[:1000]
                await session.commit()
                return ReconciliationResult(processed=True)

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
            or not isinstance(states, list)
            or not states
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
            integration.sync_status, integration.last_error = "READY", None
        except Exception as exc:  # noqa: BLE001 - one bounded poll, sanitized operator evidence
            integration.sync_status, integration.last_error = (
                "FAILED",
                f"V2 Linear poll failed: {type(exc).__name__}",
            )
            imported = updated = 0
        await session.commit()
        return ReconciliationResult(processed=True, imported=imported, updated=updated)

    @staticmethod
    async def _session_integration(session: AsyncSession) -> Integration | None:
        integration: Integration | None = await session.scalar(
            select(Integration).where(Integration.provider_name == "linear")
        )
        return integration

    async def _linear_integration(self, session: AsyncSession, node: WorkflowNode) -> Integration:
        allowed = {str(value) for value in node.integration_ids or []}
        integration = await session.scalar(
            select(Integration).where(Integration.provider_name == "linear")
        )
        if (
            integration is None
            or str(integration.id) not in allowed
            or integration.encrypted_credentials is None
        ):
            raise RuntimeError("Select a configured Linear integration for Intake")
        if not node.filter_state_ids:
            raise RuntimeError("Select at least one Linear source state")
        return integration

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
            await enqueue_job(
                session,
                task,
                JobRole.DELIVERER,
                "INTERPRET_TASK",
                payload={"source": "linear", "linear_issue_id": issue["id"], "raw": issue["raw"]},
            )
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
        if task.execution_version == 1:
            task.started_at = linear_datetime(issue["raw"].get("startedAt"))
            task.completed_at = linear_datetime(issue["raw"].get("completedAt"))
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
