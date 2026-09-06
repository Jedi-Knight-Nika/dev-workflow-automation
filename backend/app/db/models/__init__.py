"""SQLAlchemy model registry grouped by domain.

Importing this package registers every table and preserves the historical
``from app.db.models import ...`` API.
"""

from app.domain.operational_states import IndexStatus, IntegrationStatus, JobRole, JobState
from app.domain.tasks import TaskState

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
from .tasks import (
    AgentCheckpoint,
    ExternalTaskSnapshot,
    Job,
    JobContext,
    ReviewFinding,
    Task,
    TaskEvent,
    TaskMemory,
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
    "AccountSettings",
    "AgentCheckpoint",
    "AgentConfig",
    "AgentKnowledgeChunk",
    "AgentKnowledgeSource",
    "ApprovalRequest",
    "ExecutionPolicy",
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
    "Notification",
    "NotificationDelivery",
    "Repository",
    "ReviewFinding",
    "Role",
    "SettingsAuditEvent",
    "Task",
    "TaskAssignment",
    "TaskEvent",
    "TaskMemory",
    "TaskState",
    "Team",
    "TelegramConnection",
    "TelegramConnectionToken",
    "TelegramUpdate",
    "TerminalEvent",
    "TerminalSession",
    "ToolExecutionEvent",
    "ValidationRecord",
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
