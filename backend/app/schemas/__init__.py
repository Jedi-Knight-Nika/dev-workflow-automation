"""Public API schema registry grouped by feature."""

from .agents import (
    AgentConfigRead,
    AgentConfigUpdate,
    AgentKnowledgeCreate,
    AgentKnowledgeRead,
)
from .dashboard import (
    DashboardActivityRead,
)
from .execution import (
    ApprovalResolution,
    ExecutionPolicyRead,
    ExecutionPolicyWrite,
)
from .integrations import (
    DiscoveredRepository,
    IntegrationRead,
    IntegrationUpdate,
    KnowledgeSearchResult,
    LinearMemberRead,
    LinearWorkflowStateRead,
    MergeResult,
    ProviderCatalogRead,
    ProviderModelRead,
    PullRequestRead,
    RepositoryCreate,
    RepositoryRead,
    TelegramConfigure,
    WebhookHealthRead,
)
from .tasks import (
    EventRead,
    ExternalTaskRead,
    JobCreate,
    JobRead,
    TaskCreate,
    TaskRead,
)
from .teams import (
    RoleClone,
    RoleRead,
    RoleWrite,
    TaskAssignmentCreate,
    TaskAssignmentRead,
    TeamRead,
    TeamWrite,
)
from .terminals import (
    TerminalAccessRead,
    TerminalOpen,
)
from .workers import (
    ReviewFindingRead,
    ValidationRead,
    WorkerNodeRead,
    WorkerResult,
)
from .workflows import (
    WorkflowEdgeRead,
    WorkflowGraphRead,
    WorkflowNodeModelValidationRead,
    WorkflowNodeRead,
)

__all__ = [
    "AgentConfigRead",
    "AgentConfigUpdate",
    "AgentKnowledgeCreate",
    "AgentKnowledgeRead",
    "ApprovalResolution",
    "DashboardActivityRead",
    "DiscoveredRepository",
    "EventRead",
    "ExecutionPolicyRead",
    "ExecutionPolicyWrite",
    "ExternalTaskRead",
    "IntegrationRead",
    "IntegrationUpdate",
    "JobCreate",
    "JobRead",
    "KnowledgeSearchResult",
    "LinearMemberRead",
    "LinearWorkflowStateRead",
    "MergeResult",
    "ProviderCatalogRead",
    "ProviderModelRead",
    "PullRequestRead",
    "RepositoryCreate",
    "RepositoryRead",
    "ReviewFindingRead",
    "RoleClone",
    "RoleRead",
    "RoleWrite",
    "TaskAssignmentCreate",
    "TaskAssignmentRead",
    "TaskCreate",
    "TaskRead",
    "TeamRead",
    "TeamWrite",
    "TelegramConfigure",
    "TerminalAccessRead",
    "TerminalOpen",
    "ValidationRead",
    "WebhookHealthRead",
    "WorkerNodeRead",
    "WorkerResult",
    "WorkflowEdgeRead",
    "WorkflowGraphRead",
    "WorkflowNodeModelValidationRead",
    "WorkflowNodeRead",
]
