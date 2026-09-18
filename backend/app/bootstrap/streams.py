from functools import lru_cache

from sqlalchemy import func, select

from app.activity.infrastructure.models import ActivityEvent
from app.bootstrap.activity import activity_sessions
from app.bootstrap.dependencies import get_event_queries
from app.platform.scheduling.stream_signal import StreamSignal


async def activity_watermark() -> int:
    async with activity_sessions()() as session:
        return int(await session.scalar(select(func.max(ActivityEvent.sequence))) or 0)


@lru_cache
def task_signal() -> StreamSignal:
    return StreamSignal(get_event_queries().latest_id)


@lru_cache
def activity_signal() -> StreamSignal:
    return StreamSignal(activity_watermark)
