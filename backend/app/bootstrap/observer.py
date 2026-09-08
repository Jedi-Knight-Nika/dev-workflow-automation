"""Optional composition, with bounded pools/timeouts independent of execution."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

import asyncpg  # type: ignore[import-untyped]
import structlog
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bootstrap.observability import (
    get_analytics_queries,
    get_observability_queries,
    get_observability_store,
)
from app.observability.observer.application import Observer
from app.observability.observer.instrumentation import record
from app.observability.observer.local_model import OllamaObserver
from app.observability.observer.persistence import SqlObserverStore
from app.observability.observer.reads import ProductObserverReads
from app.platform.configuration.settings import get_settings


@lru_cache
def observer_sessions() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        get_settings().database_url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": "2500", "lock_timeout": "250"}},
    )
    return async_sessionmaker(engine, expire_on_commit=False)


@lru_cache
def get_observer() -> Observer:
    settings = get_settings()
    store = SqlObserverStore(observer_sessions(), settings.observer_proactive_cooldown_seconds)
    model = (
        OllamaObserver(settings.ollama_base_url, settings.observer_model)
        if settings.observer_local_ai_enabled
        else None
    )
    return Observer(
        ProductObserverReads(
            observer_sessions(),
            get_observability_queries,
            get_analytics_queries,
            get_observability_store(),
        ),
        store,
        model,
        local_enabled=settings.observer_local_ai_enabled,
        reserve_mb=settings.observer_min_available_memory_mb,
        record=record,
        thresholds={
            "cpu": settings.observability_cpu_warning,
            "memory": settings.observability_ram_warning,
            "disk": settings.observability_disk_warning,
        },
    )


class ObserverRuntime:
    """Push-driven switch: disabled means no detection timer or inference job.

    One idle database LISTEN connection carries configuration changes across API
    and controller processes; it does not poll tasks or metrics while disabled.
    """

    def __init__(self) -> None:
        self.enabled = False
        self.values: dict[str, object] = {}
        self.active: set[asyncio.Task[object]] = set()
        self.detector: asyncio.Task[None] | None = None
        self.worker = False

    async def configure(self, changes: dict[str, object] | None = None) -> dict[str, object]:
        settings = get_settings()
        values = await get_observer().store.preference("deployment", changes)
        config = {
            "enabled": settings.observer_enabled and values.get("enabled", True),
            "display_name": values.get("display_name", "Jarvis"),
            "local_ai_enabled": settings.observer_local_ai_enabled,
            "model": settings.observer_model,
            "memory_reserve_mb": settings.observer_min_available_memory_mb,
        }
        await self.apply(config)
        if changes is not None:
            async with observer_sessions()() as session, session.begin():
                from sqlalchemy import text

                await session.execute(text("SELECT pg_notify('observer_configuration', 'changed')"))
        return config

    async def apply(self, config: dict[str, object]) -> None:
        was_enabled = self.enabled
        self.values, self.enabled = config, bool(config["enabled"])
        if not self.enabled:
            active = tuple(self.active)
            for task in active:
                task.cancel()
            if active:
                await asyncio.wait(active, timeout=3)
            if self.detector:
                self.detector.cancel()
                await asyncio.gather(self.detector, return_exceptions=True)
                self.detector = None
            # Release cached task/resource projections when the feature is off.
            reads = get_observer().reads
            if isinstance(reads, ProductObserverReads):
                reads.cache.clear()
            if was_enabled:
                from sqlalchemy import update

                from app.observability.observer.models import ObserverQuestion

                async with observer_sessions()() as session, session.begin():
                    await session.execute(
                        update(ObserverQuestion)
                        .where(ObserverQuestion.status.in_(["PENDING", "RUNNING"]))
                        .values(status="INTERRUPTED")
                    )
        elif self.worker and self.detector is None:
            self.detector = asyncio.create_task(run_attention(), name="observer-read-only")

    async def listen(self) -> None:
        changed = asyncio.Event()
        while True:
            connection = None
            try:
                connection = await asyncpg.connect(
                    str(
                        make_url(get_settings().database_url)
                        .set(drivername="postgresql")
                        .render_as_string(hide_password=False)
                    ),
                    timeout=3,
                )
                await connection.add_listener("observer_configuration", lambda *_: changed.set())
                connection.add_termination_listener(lambda _: changed.set())
                await self.configure()
                while not connection.is_closed():
                    await changed.wait()
                    changed.clear()
                    await self.configure()
            except Exception:  # noqa: BLE001 -- optional process boundary, fail closed
                await self.apply({"enabled": False})
                await asyncio.sleep(5)
            finally:
                if connection:
                    await connection.close(timeout=2)


observer_runtime = ObserverRuntime()


async def run_attention() -> None:
    log = structlog.get_logger()
    tick = 0
    while True:
        try:
            async with asyncio.timeout(18):
                observer = get_observer()
                await observer.detect_attention()
                if tick % 60 == 0:
                    await observer.store.cleanup()
            tick += 1
        except Exception:  # noqa: BLE001 -- supporting worker must not escape into execution
            # No exception payloads, shared retries, or lifecycle writes.
            log.warning("observer_attention_unavailable")
        await asyncio.sleep(60)


@asynccontextmanager
async def observer_controller(worker: bool = True) -> AsyncIterator[None]:
    observer_runtime.worker = worker
    task = (
        asyncio.create_task(observer_runtime.listen(), name="observer-configuration-listener")
        if get_settings().observer_enabled
        else None
    )
    try:
        yield
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await observer_runtime.apply({"enabled": False})
