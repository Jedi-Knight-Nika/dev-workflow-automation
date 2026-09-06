import uuid

import pytest

from app.application.dispatch_jobs import DispatchJobs
from app.application.ports.job_dispatch import ClaimedJob


class FakeJobDispatch:
    def __init__(self, claimed_job: ClaimedJob | None) -> None:
        self.claimed_job = claimed_job
        self.prepared: list[ClaimedJob] = []

    async def claim(self) -> ClaimedJob | None:
        return self.claimed_job

    async def prepare(self, claimed_job: ClaimedJob) -> bool:
        self.prepared.append(claimed_job)
        return claimed_job == self.claimed_job


@pytest.mark.asyncio
async def test_dispatch_jobs_delegates_claim_and_preparation() -> None:
    claimed_job = ClaimedJob(uuid.uuid4(), uuid.uuid4())
    adapter = FakeJobDispatch(claimed_job)
    use_case = DispatchJobs(adapter)

    claimed = await use_case.claim()

    assert claimed == claimed_job
    assert await use_case.prepare(claimed_job)
    assert adapter.prepared == [claimed_job]
