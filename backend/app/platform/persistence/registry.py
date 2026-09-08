"""Composition registry for the current database schema."""

from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession, PricingCatalog
from app.delivery.infrastructure.status_sync import ExternalStatusSync
from app.engineering.domain.lifecycle import TaskStatus
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.models import ReviewCycle, TaskPhaseRun, ValidationRun
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent, TaskRepositoryScope
from app.intake.infrastructure.models import LocalModelRun
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
from app.intake.infrastructure.webhook_models import WebhookDelivery
from app.platform.configuration.models import AccountSettings, SettingsAuditEvent
from app.platform.integrations.models import Integration
from app.platform.scheduling.models import WorkerNode
from app.platform.scheduling.states import IntegrationStatus, JobState
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.automation import TeamAutomationPolicy
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import TaskAssignment, Team

__all__ = [
    "AIRun",
    "AccountSettings",
    "DeveloperSession",
    "ExternalStatusSync",
    "ExternalTaskSnapshot",
    "Integration",
    "IntegrationStatus",
    "Job",
    "JobState",
    "LocalModelRun",
    "PricingCatalog",
    "Repository",
    "ReviewCycle",
    "SettingsAuditEvent",
    "Task",
    "TaskAssignment",
    "TaskEvent",
    "TaskMessage",
    "TaskPhaseRun",
    "TaskRepositoryScope",
    "TaskStatus",
    "Team",
    "TeamAgentProfile",
    "TeamAutomationPolicy",
    "ValidationRun",
    "WebhookDelivery",
    "WorkerNode",
]
