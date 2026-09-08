"""SQLAlchemy model registry grouped by domain.

Importing this package registers every table and preserves the historical
``from app.db.models import ...`` API.
"""

from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession, PricingCatalog
from app.delivery.infrastructure.status_sync import ExternalStatusSync
from app.domain.operational_states import IndexStatus, IntegrationStatus, JobRole, JobState
from app.domain.tasks import TaskState
from app.engineering.infrastructure.models import ReviewCycle, TaskPhaseRun, ValidationRun
from app.intake.infrastructure.models import LocalModelRun
from app.teams.infrastructure.automation import TeamAutomationPolicy
from app.teams.infrastructure.models import TeamAgentProfile

from .agents import (
    AgentConfig,
    AgentKnowledgeChunk,
    AgentKnowledgeSource,
    AIAgent,
    Role,
)
from .execution import (
    ApprovalRequest,
    ExecutionPolicy,
    ToolExecutionEvent,
    WorkerNode,
    WorkerRun,
)
from .integrations import (
    Integration,
    Repository,
    WebhookDelivery,
)
from .notifications import (
    Incident,
    Notification,
    NotificationDelivery,
    TelegramConnection,
    TelegramConnectionToken,
    TelegramUpdate,
)
from .resilience import FailureEvent, HealthState, JobRetryState
from .settings import AccountSettings, SettingsAuditEvent
from .task_messages import TaskMessage
from .tasks import (
    AgentCheckpoint,
    ExternalTaskSnapshot,
    Job,
    JobContext,
    ReviewFinding,
    Task,
    TaskEvent,
    TaskMemory,
    TaskRepositoryScope,
    ValidationRecord,
    WorkspaceLease,
)
from .teams import (
    TaskAssignment,
    Team,
)
from .terminals import (
    TerminalEvent,
    TerminalSession,
)
from .workflows import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowRevision,
    WorkflowTransition,
)

__all__ = [
    "AIAgent",
    "AIRun",
    "AccountSettings",
    "AgentCheckpoint",
    "AgentConfig",
    "AgentKnowledgeChunk",
    "AgentKnowledgeSource",
    "ApprovalRequest",
    "DeveloperSession",
    "ExecutionPolicy",
    "ExternalStatusSync",
    "ExternalTaskSnapshot",
    "FailureEvent",
    "HealthState",
    "Incident",
    "IndexStatus",
    "Integration",
    "IntegrationStatus",
    "Job",
    "JobContext",
    "JobRetryState",
    "JobRole",
    "JobState",
    "LocalModelRun",
    "Notification",
    "NotificationDelivery",
    "PricingCatalog",
    "Repository",
    "ReviewCycle",
    "ReviewFinding",
    "Role",
    "SettingsAuditEvent",
    "Task",
    "TaskAssignment",
    "TaskEvent",
    "TaskMemory",
    "TaskMessage",
    "TaskPhaseRun",
    "TaskRepositoryScope",
    "TaskState",
    "Team",
    "TeamAgentProfile",
    "TeamAutomationPolicy",
    "TelegramConnection",
    "TelegramConnectionToken",
    "TelegramUpdate",
    "TerminalEvent",
    "TerminalSession",
    "ToolExecutionEvent",
    "ValidationRecord",
    "ValidationRun",
    "WebhookDelivery",
    "WorkerNode",
    "WorkerRun",
    "WorkflowDefinition",
    "WorkflowEdge",
    "WorkflowNode",
    "WorkflowRevision",
    "WorkflowTransition",
    "WorkspaceLease",
]
