from app.application.jobs import (
    CompleteExecutorJob,
    CompleteFailedJob,
    CompleteIntakeJob,
    CompleteReviewerJob,
    CompleteTesterJob,
    CompleteThinkerJob,
)
from app.application.manage_worker_presence import ManageWorkerPresence
from app.application.process_deliveries import ProcessDeliveries
from app.application.process_indexes import ProcessIndexes
from app.application.reconcile_tasks import ReconcileExternalTasks
from app.application.recover_resources import RecoveryManager
from app.application.run_startup_maintenance import RunStartupMaintenance
from app.config import Settings
from app.db.session import SessionLocal
from app.domain.jobs import RetryPolicy
from app.infrastructure.delivery_processing import SqlAlchemyDeliveryProcessor
from app.infrastructure.index_processing import SqlAlchemyIndexProcessor
from app.infrastructure.job_dispatch import SqlAlchemyJobDispatch
from app.infrastructure.linear_reconciliation import SqlAlchemyLinearTaskReconciliation
from app.infrastructure.persistence.executor_completion import (
    SqlAlchemyExecutorCompletionUnitOfWorkFactory,
)
from app.infrastructure.persistence.intake_completion import (
    SqlAlchemyIntakeCompletionUnitOfWorkFactory,
)
from app.infrastructure.persistence.job_completion import (
    SqlAlchemyFailedCompletionUnitOfWorkFactory,
)
from app.infrastructure.persistence.resilience import SqlAlchemyResilienceStore
from app.infrastructure.persistence.reviewer_completion import (
    SqlAlchemyReviewerCompletionUnitOfWorkFactory,
)
from app.infrastructure.persistence.tester_completion import (
    SqlAlchemyTesterCompletionUnitOfWorkFactory,
)
from app.infrastructure.persistence.thinker_completion import (
    SqlAlchemyThinkerCompletionUnitOfWorkFactory,
)
from app.infrastructure.scheduler import Scheduler
from app.infrastructure.startup_maintenance import SqlAlchemyStartupMaintenance
from app.infrastructure.worker_presence import SqlAlchemyWorkerPresence
from app.infrastructure.workers import ConfiguredWorkerRunner


def create_scheduler(settings: Settings) -> Scheduler:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    failed_completer = CompleteFailedJob(
        SqlAlchemyFailedCompletionUnitOfWorkFactory(SessionLocal),
        RetryPolicy(settings.max_job_attempts, settings.job_retry_base_seconds),
    )
    intake_completer = CompleteIntakeJob(
        SqlAlchemyIntakeCompletionUnitOfWorkFactory(
            SessionLocal,
            settings.max_executor_jobs_per_task,
            settings.max_thinker_jobs_per_task,
        )
    )
    thinker_completer = CompleteThinkerJob(
        SqlAlchemyThinkerCompletionUnitOfWorkFactory(SessionLocal)
    )
    executor_completer = CompleteExecutorJob(
        SqlAlchemyExecutorCompletionUnitOfWorkFactory(
            SessionLocal,
            settings.max_executor_jobs_per_task,
            settings.max_thinker_jobs_per_task,
        )
    )
    tester_completer = CompleteTesterJob(SqlAlchemyTesterCompletionUnitOfWorkFactory(SessionLocal))
    reviewer_completer = CompleteReviewerJob(
        SqlAlchemyReviewerCompletionUnitOfWorkFactory(
            SessionLocal,
            settings.max_executor_jobs_per_task,
            settings.max_thinker_jobs_per_task,
            settings.max_same_finding_repeats,
        ),
        settings.max_same_finding_repeats,
    )
    delivery_processor = ProcessDeliveries(SqlAlchemyDeliveryProcessor(SessionLocal))
    index_processor = ProcessIndexes(SqlAlchemyIndexProcessor(SessionLocal))
    startup_maintenance = RunStartupMaintenance(
        SqlAlchemyStartupMaintenance(
            SessionLocal,
            settings.workspace_root,
            settings.archived_workspace_retention_days,
        )
    )
    worker_presence = ManageWorkerPresence(SqlAlchemyWorkerPresence(SessionLocal, worker_id))
    job_dispatch = DispatchJobs(
        SqlAlchemyJobDispatch(SessionLocal, worker_id, settings.worker_lease_seconds)
    )
    return Scheduler(
        settings,
        worker_id,
        job_dispatch,
        ConfiguredWorkerRunner(settings),
        failed_completer,
        intake_completer,
        thinker_completer,
        executor_completer,
        tester_completer,
        reviewer_completer,
        delivery_processor,
        index_processor,
        startup_maintenance,
        worker_presence,
        ReconcileExternalTasks(SqlAlchemyLinearTaskReconciliation(SessionLocal)),
        RecoveryManager(SqlAlchemyResilienceStore(SessionLocal)),
    )


import os
import socket

from app.application.dispatch_jobs import DispatchJobs
