"""Activity composition owns its small pool; execution never imports this module."""

import asyncio
from functools import lru_cache

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.activity.application.ports import ActivityMonitor, ActivityQueries
from app.activity.application.project import ProjectActivity
from app.activity.infrastructure.maintenance import SqlActivityMaintenance
from app.activity.infrastructure.monitoring import activity_monitoring
from app.activity.infrastructure.projector import ActivityProjector
from app.activity.infrastructure.queries import SqlActivityQueries
from app.platform.configuration.settings import get_settings


@lru_cache
def activity_sessions() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        get_settings().database_url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=1,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": "2000", "lock_timeout": "100"}},
    )
    return async_sessionmaker(engine, expire_on_commit=False)


def get_activity_queries() -> ActivityQueries:
    settings = get_settings()
    return SqlActivityQueries(
        activity_sessions(),
        settings.activity_max_events,
        settings.activity_max_tasks,
        settings.activity_max_files,
        settings.activity_collect_files,
    )


def get_activity_monitor() -> ActivityMonitor:
    return activity_monitoring


def create_activity_projector() -> ProjectActivity:
    settings = get_settings()
    sessions = activity_sessions()
    return ProjectActivity(
        ActivityProjector(sessions),
        SqlActivityMaintenance(
            sessions,
            settings.workspace_root,
            collect_files_enabled=settings.activity_collect_files,
            retention_days=settings.activity_file_retention_days,
        ),
    )


async def render_activity_metrics() -> bytes:
    if get_settings().activity_enabled:
        try:
            await asyncio.wait_for(get_activity_queries().projection_status(), timeout=1)
        except (SQLAlchemyError, TimeoutError, OSError):
            activity_monitoring.lag.set(-1)
    return activity_monitoring.render()
