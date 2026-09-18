import asyncio
from dataclasses import replace
from uuid import uuid4

from app.engineering.domain.lifecycle import Action, WaitReason
from tests.contracts.support import PhaseJobsHarness


async def test_exclusive_claims_across_competing_workers(phase_jobs_contract: PhaseJobsHarness):
    harness = phase_jobs_contract
    task_ids = {await harness.seed() for _ in range(4)}
    leases = await asyncio.gather(*(harness.jobs.claim() for _ in range(8)))
    claimed = [lease for lease in leases if lease is not None]
    assert len(claimed) == 4
    assert {lease.task_id for lease in claimed} == task_ids
    assert len({lease.token for lease in claimed}) == 4


async def test_completion_is_atomic_and_duplicate_safe(phase_jobs_contract: PhaseJobsHarness):
    harness = phase_jobs_contract
    task_id = await harness.seed()
    lease = await harness.jobs.claim()
    assert lease is not None
    await harness.jobs.complete(lease, Action.START)
    completed = await harness.snapshot(task_id)
    assert (completed.status, completed.stage, completed.version) == ("ACTIVE", "DEVELOPING", 2)
    assert completed.queued_actions == ("DEVELOPER_TURN",)
    await harness.jobs.complete(lease, Action.START)
    assert await harness.snapshot(task_id) == completed


async def test_wrong_token_cannot_mutate_or_renew_work(phase_jobs_contract: PhaseJobsHarness):
    harness = phase_jobs_contract
    task_id = await harness.seed()
    lease = await harness.jobs.claim()
    assert lease is not None
    stale = replace(lease, token=uuid4())
    before = await harness.snapshot(task_id)
    assert not await harness.jobs.heartbeat(stale)
    await harness.jobs.complete(stale, Action.START)
    await harness.jobs.block(stale, WaitReason.MISSING_CONFIGURATION, "Stale caller")
    assert await harness.snapshot(task_id) == before
    assert await harness.jobs.heartbeat(lease)


async def test_revoked_authority_rejects_late_results(phase_jobs_contract: PhaseJobsHarness):
    harness = phase_jobs_contract
    task_id = await harness.seed()
    lease = await harness.jobs.claim()
    assert lease is not None
    await harness.pause(task_id)
    paused = await harness.snapshot(task_id)
    assert not await harness.jobs.heartbeat(lease)
    await harness.jobs.complete(lease, Action.START)
    assert await harness.snapshot(task_id) == paused


async def test_expired_work_is_blocked_not_automatically_replayed(
    phase_jobs_contract: PhaseJobsHarness,
):
    harness = phase_jobs_contract
    task_id = await harness.seed()
    lease = await harness.jobs.claim()
    assert lease is not None
    await harness.expire(lease)
    await harness.jobs.recover()
    state = await harness.snapshot(task_id)
    assert state.status == "WAITING_HUMAN" and not state.queued_actions
    assert await harness.jobs.claim() is None
    assert not await harness.jobs.heartbeat(lease)
