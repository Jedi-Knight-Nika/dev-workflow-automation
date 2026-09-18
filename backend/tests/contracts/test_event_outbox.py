import asyncio

from tests.contracts.support import OutboxHarness


async def test_exclusive_claims_and_confirmed_completion(outbox_contract: OutboxHarness):
    harness = outbox_contract
    expected = {await harness.seed() for _ in range(4)}
    results = await asyncio.gather(*(harness.outbox.claim() for _ in range(8)))
    claims = [claim for claim in results if claim is not None]
    assert len(claims) == 4
    assert {claim.event.event_id for claim in claims} == expected
    for claim in claims:
        assert not await harness.is_published(claim.event.event_id)
        await harness.outbox.published(claim)
        await harness.outbox.published(claim)
        assert await harness.is_published(claim.event.event_id)
    assert await harness.outbox.claim() is None


async def test_retry_delays_delivery_and_preserves_identity(outbox_contract: OutboxHarness):
    harness = outbox_contract
    identifier = await harness.seed()
    first = await harness.outbox.claim()
    assert first is not None
    await harness.outbox.retry(first, "TimeoutError")
    assert await harness.outbox.claim() is None
    assert not await harness.is_published(identifier)
    await harness.make_due(identifier)
    second = await harness.outbox.claim()
    assert second is not None
    assert first.event == second.event and first.token != second.token


async def test_expired_owner_cannot_finish_or_release_a_new_claim(outbox_contract: OutboxHarness):
    harness = outbox_contract
    identifier = await harness.seed()
    first = await harness.outbox.claim()
    assert first is not None
    await harness.make_due(identifier)
    second = await harness.outbox.claim()
    assert second is not None and first.token != second.token
    await harness.outbox.published(first)
    await harness.outbox.retry(first, "OldOwner")
    assert not await harness.is_published(identifier)
    assert await harness.outbox.claim() is None
    await harness.outbox.published(second)
    assert await harness.is_published(identifier)
