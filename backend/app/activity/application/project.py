from app.activity.application.ports import ActivityMaintenance, ActivityProjection


class ProjectActivity:
    def __init__(self, projection: ActivityProjection, maintenance: ActivityMaintenance) -> None:
        self.projection, self.maintenance = projection, maintenance

    async def execute(self, *, maintain: bool = True) -> int:
        projected = await self.projection.project()
        if maintain:
            await self.maintenance.collect()
            await self.maintenance.expire()
        return projected
