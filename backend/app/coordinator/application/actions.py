"""Bounded external delivery; uncertain effects are reconciled, never blindly resent."""

import asyncio

from app.coordinator.application.ports import ConversationGateway, CoordinationActions

DELIVERY_CHECK_TIMEOUT_SECONDS = 45


class ExecuteCoordinatorActions:
    def __init__(self, actions: CoordinationActions, conversations: ConversationGateway) -> None:
        self.actions, self.conversations = actions, conversations

    async def execute_one(self) -> bool:
        return await self.actions.execute_one()

    async def recover(self) -> None:
        await self.actions.recover()

    async def deliver_one(self) -> bool:
        claim = await self.actions.claim_delivery()
        delivery = claim.delivery
        if delivery is None:
            return claim.handled
        try:
            async with asyncio.timeout(45):
                reference = (
                    await self.conversations.request_review(delivery.task_id, delivery.action_id)
                    if delivery.kind == "REQUEST_REVIEW"
                    else await self.conversations.reply(
                        delivery.task_id, delivery.provider, delivery.message, delivery.action_id
                    )
                )
        except Exception as exc:  # noqa: BLE001 -- persist a sanitized failure at the worker/effect boundary
            await self.actions.fail_delivery(
                delivery,
                f"Delivery not confirmed ({type(exc).__name__}); inspect the original conversation before retrying",
                reconcile=delivery.kind != "REQUEST_REVIEW",
            )
        else:
            await self.actions.complete_delivery(delivery, reference)
        return True

    async def reconcile_one(self) -> bool:
        delivery = await self.actions.claim_reconciliation()
        if delivery is None:
            return False
        error = "Delivery still uncertain; bounded provider history did not identify a unique matching message. No resend occurred."
        reference = None
        try:
            async with asyncio.timeout(DELIVERY_CHECK_TIMEOUT_SECONDS):
                reference = await self.conversations.reconcile(
                    delivery.task_id,
                    delivery.provider,
                    delivery.message,
                    delivery.action_id,
                    delivery.attempted_at,
                    delivery.kind,
                )
        except Exception as exc:  # noqa: BLE001 -- sanitize provider errors at the effect boundary
            error = f"Delivery verification unavailable ({type(exc).__name__}); no resend occurred"
        await self.actions.complete_reconciliation(delivery, reference, error)
        return True
