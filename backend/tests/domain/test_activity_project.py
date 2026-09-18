from unittest.mock import AsyncMock

from app.activity.application.project import ProjectActivity


async def test_polling_keeps_projection_and_maintenance_order():
    order = []
    projection = AsyncMock()
    maintenance = AsyncMock()
    projection.project.side_effect = lambda: order.append("project") or 3
    maintenance.collect.side_effect = lambda: order.append("collect")
    maintenance.expire.side_effect = lambda: order.append("expire")
    assert await ProjectActivity(projection, maintenance).execute() == 3
    assert order == ["project", "collect", "expire"]


async def test_notification_does_not_repeat_expensive_maintenance():
    projection = AsyncMock(project=AsyncMock(return_value=2))
    maintenance = AsyncMock()
    assert await ProjectActivity(projection, maintenance).execute(maintain=False) == 2
    maintenance.collect.assert_not_awaited()
    maintenance.expire.assert_not_awaited()
