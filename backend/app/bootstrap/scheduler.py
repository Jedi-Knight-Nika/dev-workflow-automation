"""Composition root for the fixed-lifecycle controller.

Native harnesses own model turns. The scheduler never dispatches the retired
JSON-proposal worker, workflow graph, or repository-embedding loop.
"""

import os
import socket

from app.agent_runtime.infrastructure.orphans import reap_orphans
from app.application.manage_worker_presence import ManageWorkerPresence
from app.application.process_deliveries import ProcessDeliveries
from app.application.reconcile_tasks import ReconcileExternalTasks
from app.config import Settings
from app.db.session import SessionLocal
from app.engineering.application.jobs import RunEngineeringJob
from app.engineering.infrastructure.executor import SqlPhaseExecutor
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.infrastructure.delivery_processing import SqlAlchemyDeliveryProcessor
from app.infrastructure.linear_reconciliation import SqlAlchemyLinearTaskReconciliation
from app.infrastructure.scheduler import Scheduler
from app.infrastructure.task_reconciliation import CompositeTaskReconciliation
from app.infrastructure.trello_reconciliation import SqlAlchemyTrelloTaskReconciliation
from app.infrastructure.worker_presence import SqlAlchemyWorkerPresence


def create_scheduler(settings: Settings) -> Scheduler:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    jobs = SqlPhaseJobs(
        SessionLocal,
        worker_id,
        settings.worker_lease_seconds,
        orphan_cleanup=lambda: reap_orphans(SessionLocal, settings),
    )
    return Scheduler(
        settings=settings,
        worker_id=worker_id,
        jobs=jobs,
        worker=RunEngineeringJob(
            jobs,
            SqlPhaseExecutor(SessionLocal, settings),
            heartbeat_seconds=min(
                settings.worker_heartbeat_seconds, settings.worker_lease_seconds / 3
            ),
        ),
        deliveries=ProcessDeliveries(SqlAlchemyDeliveryProcessor(SessionLocal)),
        presence=ManageWorkerPresence(SqlAlchemyWorkerPresence(SessionLocal, worker_id)),
        reconciler=ReconcileExternalTasks(
            CompositeTaskReconciliation(
                SqlAlchemyLinearTaskReconciliation(SessionLocal),
                SqlAlchemyTrelloTaskReconciliation(SessionLocal),
            )
        ),
    )
