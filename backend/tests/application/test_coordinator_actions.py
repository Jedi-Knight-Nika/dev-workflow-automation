import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.coordinator.application.actions import ExecuteCoordinatorActions
from app.coordinator.application.ports import DeliveryClaim, OutboundDelivery


def outbound(kind="REPLY"):
    return OutboundDelivery(
        uuid4(), uuid4(), "github", "Approved response", kind, datetime.now(UTC)
    )


@pytest.mark.parametrize("handled", [False, True])
async def test_empty_or_rejected_claim_never_calls_provider(handled):
    actions = AsyncMock(claim_delivery=AsyncMock(return_value=DeliveryClaim(handled)))
    gateway = AsyncMock()
    assert await ExecuteCoordinatorActions(actions, gateway).deliver_one() is handled
    gateway.reply.assert_not_awaited()
    gateway.request_review.assert_not_awaited()


@pytest.mark.parametrize("kind", ["REPLY", "REQUEST_REVIEW"])
async def test_claim_is_committed_before_send_and_result_is_persisted_after(kind):
    delivery = outbound(kind)
    order = []

    async def claim():
        order.append("claim")
        return DeliveryClaim(True, delivery)

    async def send(*_args):
        order.append("send")
        return "provider-reference"

    actions = AsyncMock(claim_delivery=AsyncMock(side_effect=claim))
    actions.complete_delivery.side_effect = lambda *_args: order.append("complete")
    gateway = AsyncMock(
        reply=AsyncMock(side_effect=send), request_review=AsyncMock(side_effect=send)
    )
    assert await ExecuteCoordinatorActions(actions, gateway).deliver_one()
    assert order == ["claim", "send", "complete"]
    actions.complete_delivery.assert_awaited_once_with(delivery, "provider-reference")
    if kind == "REPLY":
        gateway.reply.assert_awaited_once_with(
            delivery.task_id, delivery.provider, delivery.message, delivery.action_id
        )
        gateway.request_review.assert_not_awaited()
    else:
        gateway.request_review.assert_awaited_once_with(delivery.task_id, delivery.action_id)
        gateway.reply.assert_not_awaited()


@pytest.mark.parametrize("kind", ["REPLY", "REQUEST_REVIEW"])
async def test_uncertain_delivery_does_not_resend_or_expose_provider_errors(kind):
    delivery = outbound(kind)
    actions = AsyncMock(claim_delivery=AsyncMock(return_value=DeliveryClaim(True, delivery)))
    gateway = AsyncMock()
    gateway.reply.side_effect = gateway.request_review.side_effect = OSError("password=secret")
    assert await ExecuteCoordinatorActions(actions, gateway).deliver_one()
    assert gateway.reply.await_count + gateway.request_review.await_count == 1
    actions.complete_delivery.assert_not_awaited()
    arguments = actions.fail_delivery.await_args
    assert arguments.args[0] == delivery
    assert "OSError" in arguments.args[1] and "secret" not in arguments.args[1]
    assert arguments.kwargs == {"reconcile": kind != "REQUEST_REVIEW"}


async def test_persistence_failure_after_send_is_not_reclassified_as_provider_failure():
    delivery = outbound()
    actions = AsyncMock(claim_delivery=AsyncMock(return_value=DeliveryClaim(True, delivery)))
    actions.complete_delivery.side_effect = OSError("database unavailable")
    gateway = AsyncMock(reply=AsyncMock(return_value="confirmed"))
    with pytest.raises(OSError):
        await ExecuteCoordinatorActions(actions, gateway).deliver_one()
    gateway.reply.assert_awaited_once()
    actions.fail_delivery.assert_not_awaited()


async def test_cancelled_send_leaves_durable_claim_for_recovery():
    actions = AsyncMock(claim_delivery=AsyncMock(return_value=DeliveryClaim(True, outbound())))
    gateway = AsyncMock(reply=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await ExecuteCoordinatorActions(actions, gateway).deliver_one()
    actions.complete_delivery.assert_not_awaited()
    actions.fail_delivery.assert_not_awaited()


@pytest.mark.parametrize("reference", [None, "confirmed"])
async def test_reconciliation_only_reads_and_records_evidence(reference):
    delivery = outbound()
    actions = AsyncMock(claim_reconciliation=AsyncMock(return_value=delivery))
    gateway = AsyncMock(reconcile=AsyncMock(return_value=reference))
    assert await ExecuteCoordinatorActions(actions, gateway).reconcile_one()
    gateway.reconcile.assert_awaited_once_with(
        delivery.task_id,
        delivery.provider,
        delivery.message,
        delivery.action_id,
        delivery.attempted_at,
        delivery.kind,
    )
    gateway.reply.assert_not_awaited()
    gateway.request_review.assert_not_awaited()
    assert actions.complete_reconciliation.await_args.args[:2] == (delivery, reference)


async def test_reconciliation_timeout_stays_unknown_without_a_resend(monkeypatch):
    monkeypatch.setattr("app.coordinator.application.actions.DELIVERY_CHECK_TIMEOUT_SECONDS", 0.001)
    actions = AsyncMock(claim_reconciliation=AsyncMock(return_value=outbound()))

    async def wait(*_args):
        await asyncio.Event().wait()

    gateway = AsyncMock(reconcile=AsyncMock(side_effect=wait))
    assert await ExecuteCoordinatorActions(actions, gateway).reconcile_one()
    result = actions.complete_reconciliation.await_args.args
    assert result[1] is None and "TimeoutError" in result[2]
    gateway.reply.assert_not_awaited()
