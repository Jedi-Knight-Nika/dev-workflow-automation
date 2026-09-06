from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.task_reconciliation import ReconciliationResult
from app.db.models import ExternalTaskSnapshot, Integration, IntegrationStatus, JobRole, Task
from app.domain.webhooks import configured_repository_id
from app.infrastructure.persistence.job_operations import enqueue_job, record_event
from app.infrastructure.persistence.team_routing import assign_routed_team
from app.infrastructure.security.crypto import cipher
from app.integrations.trello import TrelloCard, TrelloClient, trello_datetime, trello_priority


class SqlAlchemyTrelloTaskReconciliation:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def reconcile_due(self) -> ReconciliationResult:
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            integration = await session.scalar(
                select(Integration)
                .where(
                    Integration.provider_name == "trello",
                    Integration.status == IntegrationStatus.CONNECTED,
                )
                .with_for_update(skip_locked=True)
            )
            if integration is None or integration.encrypted_credentials is None:
                return ReconciliationResult(processed=False)
            configuration = dict(integration.configuration or {})
            if not configuration.get("sync_enabled", True):
                return ReconciliationResult(processed=False)
            interval = max(int(configuration.get("poll_interval_seconds") or 60), 15)
            if (
                integration.last_synced_at is not None
                and integration.last_synced_at + timedelta(seconds=interval) > now
            ):
                return ReconciliationResult(processed=False)
            board_id = str(configuration.get("board_id") or "").strip()
            if not board_id:
                integration.sync_status = "FAILED"
                integration.last_error = "Select a Trello board to import cards"
                integration.last_synced_at = now
                await session.commit()
                return ReconciliationResult(processed=True)
            integration.sync_status = "RUNNING"
            try:
                cards = await TrelloClient(
                    cipher.decrypt(integration.encrypted_credentials)
                ).list_cards(
                    board_id,
                    {str(value) for value in configuration.get("list_ids") or []},
                )
                imported = updated = 0
                for card in cards:
                    created = await self._upsert_card(session, integration, card)
                    imported += int(created)
                    updated += int(not created)
                integration.sync_status = "READY"
                integration.last_error = None
                integration.last_synced_at = now
                await session.commit()
                return ReconciliationResult(processed=True, imported=imported, updated=updated)
            except Exception as exc:  # noqa: BLE001 - persist safe operator context
                integration.sync_status = "FAILED"
                integration.last_error = str(exc)[:1000]
                integration.last_synced_at = now
                await session.commit()
                return ReconciliationResult(processed=True)

    async def _upsert_card(
        self, session: AsyncSession, integration: Integration, card: TrelloCard
    ) -> bool:
        snapshot = await session.scalar(
            select(ExternalTaskSnapshot).where(
                ExternalTaskSnapshot.provider == "trello",
                ExternalTaskSnapshot.external_id == card["id"],
            )
        )
        task = await session.get(Task, snapshot.task_id) if snapshot else None
        created = task is None
        identifier = f"TRELLO-{card['short_link']}"
        if task is None:
            task = Task(
                external_key=identifier,
                title=card["name"],
                description=self._description(card),
                priority=trello_priority(card["labels"]),
                repository_id=configured_repository_id(integration.configuration),
            )
            session.add(task)
            await session.flush()
            await assign_routed_team(session, task, reason="trello-reconciliation")
            await enqueue_job(
                session,
                task,
                JobRole.INTAKE,
                "INTERPRET_TASK",
                payload={"source": "trello", "trello_card_id": card["id"]},
            )
            await record_event(
                session,
                task.id,
                "TASK_CREATED_FROM_TRELLO",
                {"trello_card_id": card["id"], "identifier": identifier},
                source="trello",
            )
            snapshot = ExternalTaskSnapshot(
                task_id=task.id,
                provider="trello",
                external_id=card["id"],
                identifier=identifier,
            )
            session.add(snapshot)
        else:
            task.title = card["name"]
            task.description = self._description(card)
            task.priority = trello_priority(card["labels"])
        task.due_at = trello_datetime(card["due"])
        if card["due_complete"]:
            task.completed_at = task.completed_at or datetime.now(UTC)
        assert snapshot is not None
        snapshot.state_id = card["list_id"]
        snapshot.raw_payload = card["raw"]
        snapshot.synchronized_at = datetime.now(UTC)
        return created

    @staticmethod
    def _description(card: TrelloCard) -> str:
        description = card["description"].strip()
        source = f"Trello: {card['url']}" if card["url"] else ""
        return "\n\n".join(value for value in (description, source) if value)
