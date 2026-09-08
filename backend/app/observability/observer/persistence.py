from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.observability.observer.domain import Attention, Scope
from app.observability.observer.models import (
    ObserverConversation,
    ObserverEvent,
    ObserverMessage,
    ObserverModelRun,
    ObserverPreference,
    ObserverQuestion,
)


def event_view(row: ObserverEvent) -> dict[str, Any]:
    return {
        name: str(value)
        if isinstance(value, UUID)
        else value.isoformat()
        if isinstance(value, datetime)
        else value
        for name in (
            "id",
            "kind",
            "severity",
            "status",
            "title",
            "facts",
            "source",
            "task_id",
            "team_id",
            "detected_at",
            "last_seen_at",
            "notified_at",
            "resolved_at",
            "snoozed_until",
        )
        for value in (getattr(row, name),)
    }


class SqlObserverStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], cooldown: int = 900) -> None:
        self.sessions, self.cooldown = sessions, cooldown

    async def synchronize(
        self, attention: list[Attention], sources: set[str], observed_at: str
    ) -> None:
        now = datetime.fromisoformat(observed_at)
        async with self.sessions() as session, session.begin():
            if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(782201)")):
                return
            rows = {r.fingerprint: r for r in await session.scalars(select(ObserverEvent))}
            present = {a.fingerprint for a in attention}
            for item in attention:
                row = rows.get(item.fingerprint)
                if row is None:
                    row = ObserverEvent(
                        id=uuid4(),
                        fingerprint=item.fingerprint,
                        kind=item.kind,
                        severity=item.severity,
                        status="PENDING",
                        title=item.title,
                        facts=item.facts,
                        source=item.source,
                        task_id=UUID(item.task_id) if item.task_id else None,
                        team_id=UUID(item.team_id) if item.team_id else None,
                        detected_at=now,
                        last_seen_at=now,
                    )
                    session.add(row)
                # Missing observations break the hold window, never prove recovery.
                if (
                    row.status in {"PENDING", "RESOLVED"}
                    and (now - row.last_seen_at).total_seconds() > 150
                ):
                    row.detected_at = now
                escalation = row.severity != "CRITICAL" and item.severity == "CRITICAL"
                row.title, row.facts, row.severity = item.title, item.facts, item.severity
                row.kind = item.kind
                row.last_seen_at = now
                if row.status == "RESOLVED":
                    row.detected_at, row.status, row.resolved_at = now, "PENDING", None
                    row.acknowledged_at, row.snoozed_until = None, None
                if row.status == "SNOOZED" and row.snoozed_until and row.snoozed_until <= now:
                    row.status = "OPEN"
                if escalation or (
                    row.status == "PENDING"
                    and (now - row.detected_at).total_seconds() >= item.hold_seconds
                ):
                    row.status = "OPEN"
                    if (
                        escalation
                        or row.notified_at is None
                        or (now - row.notified_at).total_seconds() >= self.cooldown
                    ):
                        row.notified_at = now
            for key, row in rows.items():
                if key not in present and row.source in sources and row.status != "RESOLVED":
                    row.status, row.resolved_at = "RESOLVED", now

    async def events(self, scope: Scope, status: str = "ACTIVE") -> list[dict[str, Any]]:
        async with self.sessions() as session:
            query = select(ObserverEvent).where(ObserverEvent.status != "PENDING")
            if status == "ACTIVE":
                query = query.where(ObserverEvent.status.in_(["OPEN", "ACKNOWLEDGED", "SNOOZED"]))
            elif status != "ALL":
                query = query.where(ObserverEvent.status == status)
            if scope.task_id:
                query = query.where(ObserverEvent.task_id == UUID(scope.task_id))
            elif scope.team_id:
                query = query.where(ObserverEvent.team_id == UUID(scope.team_id))
            return [
                event_view(r)
                for r in await session.scalars(
                    query.order_by(ObserverEvent.last_seen_at.desc()).limit(100)
                )
            ]

    async def event_action(self, identifier: str, action: str, minutes: int) -> bool:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            row = await session.get(ObserverEvent, UUID(identifier), with_for_update=True)
            if row is None or row.status in {"PENDING", "RESOLVED"}:
                return False
            if action == "acknowledge":
                row.status, row.acknowledged_at = "ACKNOWLEDGED", now
            else:
                row.status, row.snoozed_until = "SNOOZED", now + timedelta(minutes=minutes)
            return True

    async def create_question(
        self, owner: str, scope: Scope, message: str, conversation: str | None
    ) -> dict[str, str]:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            # Narrow Observer-only admission; never acquire a Team/task lock.
            if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(782202)")):
                raise OverflowError("Observer busy; try again shortly.")
            recent = await session.scalar(
                select(func.count())
                .select_from(ObserverQuestion)
                .where(ObserverQuestion.created_at > now - timedelta(minutes=1))
            )
            if recent and recent >= 12:
                raise OverflowError("Observer question limit reached; wait a minute.")
            row = (
                await session.get(ObserverConversation, UUID(conversation))
                if conversation
                else None
            )
            if conversation and (row is None or row.owner != owner or row.scope != asdict(scope)):
                raise LookupError("Conversation not found in this page scope.")
            if row is None:
                row = ObserverConversation(
                    id=uuid4(), owner=owner, scope=asdict(scope), title=message[:120]
                )
                session.add(row)
            row.updated_at = now
            identifier = uuid4()
            session.add(ObserverMessage(conversation_id=row.id, role="user", content=message))
            session.add(
                ObserverQuestion(
                    id=identifier,
                    conversation_id=row.id,
                    owner=owner,
                    scope=asdict(scope),
                    message=message,
                )
            )
            return {"request_id": str(identifier), "conversation_id": str(row.id)}

    async def question(self, owner: str, identifier: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = await session.get(ObserverQuestion, UUID(identifier))
            if row is None or row.owner != owner:
                return None
            return {
                "id": identifier,
                "conversation_id": str(row.conversation_id),
                "message": row.message,
                "scope": row.scope,
                "status": row.status,
                "result": row.result,
                "created_at": row.created_at.isoformat(),
            }

    async def claim_question(self, owner: str, identifier: str) -> bool:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            if not await session.scalar(text("SELECT pg_try_advisory_xact_lock(782203)")):
                return False
            running = await session.scalar(
                select(func.count())
                .select_from(ObserverQuestion)
                .where(
                    ObserverQuestion.status == "RUNNING",
                    ObserverQuestion.started_at > now - timedelta(seconds=90),
                )
            )
            if running:
                return False
            row = await session.get(ObserverQuestion, UUID(identifier), with_for_update=True)
            if row is None or row.owner != owner or row.status != "PENDING":
                return False
            if now - row.created_at > timedelta(minutes=5):
                return False
            row.status, row.started_at = "RUNNING", now
            return True

    async def finish_question(self, owner: str, identifier: str, result: dict[str, Any]) -> None:
        async with self.sessions() as session, session.begin():
            row = await session.get(ObserverQuestion, UUID(identifier), with_for_update=True)
            if row is None or row.owner != owner or row.status != "RUNNING":
                return
            row.status, row.result = "COMPLETED", result
            session.add(
                ObserverMessage(
                    conversation_id=row.conversation_id,
                    role="assistant",
                    content=result["answer"],
                    sources=result["sources"],
                )
            )

    async def history(self, owner: str, conversation: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            row = await session.get(ObserverConversation, UUID(conversation))
            if row is None or row.owner != owner:
                raise LookupError("Conversation not found.")
            messages = list(
                await session.scalars(
                    select(ObserverMessage)
                    .where(ObserverMessage.conversation_id == row.id)
                    .order_by(ObserverMessage.created_at.desc())
                    .limit(50)
                )
            )
            return [
                {
                    "id": str(r.id),
                    "role": r.role,
                    "content": r.content,
                    "sources": r.sources,
                    "created_at": r.created_at.isoformat(),
                }
                for r in reversed(messages)
            ]

    async def conversations(self, owner: str) -> list[dict[str, Any]]:
        async with self.sessions() as session:
            return [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "scope": r.scope,
                    "updated_at": r.updated_at.isoformat(),
                }
                for r in await session.scalars(
                    select(ObserverConversation)
                    .where(ObserverConversation.owner == owner)
                    .order_by(ObserverConversation.updated_at.desc())
                    .limit(20)
                )
            ]

    async def preference(self, owner: str, changes: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self.sessions() as session, session.begin():
            await session.execute(
                insert(ObserverPreference).values(owner=owner, values={}).on_conflict_do_nothing()
            )
            row = await session.get(ObserverPreference, owner, with_for_update=True)
            assert row is not None
            if changes is not None:
                row.values = {**row.values, **changes}
                row.updated_at = datetime.now(UTC)
            return {"focus": "normal", "last_seen_at": None, **row.values}

    async def receipt(self, question: str, receipt: dict[str, Any]) -> None:
        async with self.sessions() as session, session.begin():
            row = await session.scalar(
                select(ObserverModelRun).where(ObserverModelRun.question_id == UUID(question))
            )
            if row:
                row.receipt = receipt
            else:
                session.add(ObserverModelRun(question_id=UUID(question), receipt=receipt))

    async def usage(self) -> dict[str, Any]:
        async with self.sessions() as session:
            rows = list(
                await session.scalars(
                    select(ObserverModelRun)
                    .where(ObserverModelRun.created_at >= datetime.now(UTC) - timedelta(days=30))
                    .limit(10001)
                )
            )
            return {
                "period_days": 30,
                "local_runs": len(rows[:10000]),
                "truncated": len(rows) > 10000,
                "cloud_requests": 0,
                "paid_cost_usd": "0",
                "input_tokens": sum(r.receipt.get("prompt_eval_count") or 0 for r in rows[:10000])
                if all(r.receipt.get("prompt_eval_count") is not None for r in rows)
                else None,
                "output_tokens": sum(r.receipt.get("eval_count") or 0 for r in rows[:10000])
                if all(r.receipt.get("eval_count") is not None for r in rows)
                else None,
            }

    async def cleanup(self) -> None:
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            await session.execute(
                update(ObserverQuestion)
                .where(
                    ObserverQuestion.status.in_(["RUNNING", "PENDING"]),
                    ObserverQuestion.created_at < now - timedelta(minutes=5),
                )
                .values(status="INTERRUPTED")
            )
            await session.execute(
                delete(ObserverConversation).where(
                    ObserverConversation.updated_at < now - timedelta(days=30)
                )
            )
            await session.execute(
                delete(ObserverEvent).where(
                    ObserverEvent.status.in_(["RESOLVED", "PENDING"]),
                    ObserverEvent.last_seen_at < now - timedelta(days=90),
                )
            )
