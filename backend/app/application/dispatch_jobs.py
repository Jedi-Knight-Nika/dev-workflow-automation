from app.application.ports.job_dispatch import ClaimedJob, JobDispatch


class DispatchJobs:
    def __init__(self, dispatch: JobDispatch) -> None:
        self._dispatch = dispatch

    async def claim(self) -> ClaimedJob | None:
        return await self._dispatch.claim()

    async def prepare(self, claimed_job: ClaimedJob) -> bool:
        return await self._dispatch.prepare(claimed_job)
