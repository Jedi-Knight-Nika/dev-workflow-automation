from dataclasses import dataclass
from enum import StrEnum


class FailureClass(StrEnum):
    TRANSIENT_PROVIDER_ERROR = "TRANSIENT_PROVIDER_ERROR"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_AUTH_ERROR = "PROVIDER_AUTH_ERROR"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_PROTOCOL_ERROR = "MODEL_PROTOCOL_ERROR"
    MODEL_CONTEXT_LIMIT = "MODEL_CONTEXT_LIMIT"
    MODEL_POLICY_ERROR = "MODEL_POLICY_ERROR"
    WORKER_CRASH = "WORKER_CRASH"
    WORKER_TIMEOUT = "WORKER_TIMEOUT"
    WORKER_OOM = "WORKER_OOM"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    TOOL_INPUT_ERROR = "TOOL_INPUT_ERROR"
    GITHUB_UNAVAILABLE = "GITHUB_UNAVAILABLE"
    GITHUB_AUTH_ERROR = "GITHUB_AUTH_ERROR"
    LINEAR_UNAVAILABLE = "LINEAR_UNAVAILABLE"
    LINEAR_AUTH_ERROR = "LINEAR_AUTH_ERROR"
    RAG_UNAVAILABLE = "RAG_UNAVAILABLE"
    RAG_STALE = "RAG_STALE"
    RAG_INDEX_FAILURE = "RAG_INDEX_FAILURE"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    DATABASE_INTEGRITY_ERROR = "DATABASE_INTEGRITY_ERROR"
    IMPLEMENTATION_FAILURE = "IMPLEMENTATION_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    ARCHITECTURAL_FAILURE = "ARCHITECTURAL_FAILURE"
    REQUIREMENT_AMBIGUITY = "REQUIREMENT_AMBIGUITY"
    POLICY_DENIED = "POLICY_DENIED"
    NO_PROGRESS = "NO_PROGRESS"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    EXTERNAL_WAIT = "EXTERNAL_WAIT"
    UNKNOWN_SYSTEM_ERROR = "UNKNOWN_SYSTEM_ERROR"

    TRANSIENT_INFRA = "TRANSIENT_PROVIDER_ERROR"
    PROVIDER_AUTH = "PROVIDER_AUTH_ERROR"


class FailureScope(StrEnum):
    REQUEST = "REQUEST"
    JOB = "JOB"
    TASK = "TASK"
    PROVIDER = "PROVIDER"
    INTEGRATION = "INTEGRATION"
    WORKER_RUNTIME = "WORKER_RUNTIME"
    DATABASE = "DATABASE"
    PLATFORM = "PLATFORM"


class RecoveryAction(StrEnum):
    RETRY = "RETRY"
    WAIT_PROVIDER = "WAIT_PROVIDER"
    WAIT_INTEGRATION = "WAIT_INTEGRATION"
    WAIT_CONFIGURATION = "WAIT_CONFIGURATION"
    WAIT_HUMAN = "WAIT_HUMAN"
    WORKFLOW = "WORKFLOW"
    STOP_SECURITY = "STOP_SECURITY"
    FAIL_TERMINAL = "FAIL_TERMINAL"


@dataclass(frozen=True, slots=True)
class FailureClassification:
    failure_class: FailureClass
    scope: FailureScope
    action: RecoveryAction
    retryable: bool
    severity: str
    resource_type: str | None
    safe_message: str


def classify_failure_details(
    *, code: str | None, outcome: str | None, component: str | None = None
) -> FailureClassification:
    value = " ".join(filter(None, (code, outcome, component))).upper()
    failure_class = _class_from_text(value)
    if failure_class in {
        FailureClass.TRANSIENT_PROVIDER_ERROR,
        FailureClass.PROVIDER_RATE_LIMIT,
        FailureClass.PROVIDER_UNAVAILABLE,
    }:
        return FailureClassification(
            failure_class, FailureScope.PROVIDER, RecoveryAction.WAIT_PROVIDER, True,
            "WARNING", "PROVIDER", "AI provider is temporarily unavailable."
        )
    if failure_class in {
        FailureClass.GITHUB_UNAVAILABLE,
        FailureClass.LINEAR_UNAVAILABLE,
        FailureClass.RAG_UNAVAILABLE,
    }:
        return FailureClassification(
            failure_class, FailureScope.INTEGRATION, RecoveryAction.WAIT_INTEGRATION, True,
            "WARNING", "INTEGRATION", "A required integration is temporarily unavailable."
        )
    if failure_class in {
        FailureClass.PROVIDER_AUTH_ERROR,
        FailureClass.MODEL_UNAVAILABLE,
        FailureClass.GITHUB_AUTH_ERROR,
        FailureClass.LINEAR_AUTH_ERROR,
    }:
        provider_failure = failure_class in {
            FailureClass.PROVIDER_AUTH_ERROR, FailureClass.MODEL_UNAVAILABLE
        }
        return FailureClassification(
            failure_class,
            FailureScope.PROVIDER if provider_failure else FailureScope.INTEGRATION,
            RecoveryAction.WAIT_CONFIGURATION, False, "ACTION_REQUIRED",
            "PROVIDER" if provider_failure else "INTEGRATION",
            "Connection or model configuration requires attention."
        )
    if failure_class is FailureClass.SECURITY_INCIDENT:
        return FailureClassification(
            failure_class, FailureScope.PLATFORM, RecoveryAction.STOP_SECURITY, False,
            "CRITICAL", None, "Execution stopped because a security boundary was violated."
        )
    if failure_class in {
        FailureClass.DATABASE_UNAVAILABLE, FailureClass.DATABASE_INTEGRITY_ERROR
    }:
        return FailureClassification(
            failure_class, FailureScope.DATABASE, RecoveryAction.FAIL_TERMINAL, False,
            "CRITICAL", "DATABASE", "Authoritative persistence is unavailable or inconsistent."
        )
    if failure_class in {
        FailureClass.WORKER_CRASH, FailureClass.WORKER_TIMEOUT, FailureClass.WORKER_OOM
    }:
        return FailureClassification(
            failure_class, FailureScope.WORKER_RUNTIME, RecoveryAction.RETRY, True,
            "WARNING", "WORKER_RUNTIME", "The worker stopped before completing the Job."
        )
    if failure_class is FailureClass.MODEL_PROTOCOL_ERROR:
        return FailureClassification(
            failure_class, FailureScope.REQUEST, RecoveryAction.RETRY, True,
            "WARNING", "PROVIDER", "The model returned an invalid structured result."
        )
    if failure_class in {
        FailureClass.IMPLEMENTATION_FAILURE, FailureClass.VALIDATION_FAILURE,
        FailureClass.ARCHITECTURAL_FAILURE, FailureClass.REQUIREMENT_AMBIGUITY,
    }:
        return FailureClassification(
            failure_class, FailureScope.TASK, RecoveryAction.WORKFLOW, False,
            "WARNING", None, "Engineering work requires another workflow step."
        )
    if failure_class is FailureClass.EXTERNAL_WAIT:
        return FailureClassification(
            failure_class, FailureScope.JOB, RecoveryAction.WAIT_INTEGRATION, False,
            "INFO", "INTEGRATION", "The Job is waiting for an external event."
        )
    if failure_class in {FailureClass.POLICY_DENIED, FailureClass.NO_PROGRESS}:
        return FailureClassification(
            failure_class, FailureScope.TASK, RecoveryAction.WAIT_HUMAN, False,
            "ACTION_REQUIRED", None, "The Job cannot continue safely without user attention."
        )
    return FailureClassification(
        failure_class, FailureScope.JOB, RecoveryAction.RETRY, True,
        "WARNING", None, "The Job encountered an unexpected platform error."
    )


def classify_failure(*, code: str | None, outcome: str | None) -> FailureClass:
    """Compatibility entry point for callers that only need the taxonomy value."""
    return classify_failure_details(code=code, outcome=outcome).failure_class


def _class_from_text(value: str) -> FailureClass:
    if any(
        token in value
        for token in (
            "SECURITY",
            "SANDBOX_ESCAPE",
            "PRIVILEGE ESCALATION",
            "CREDENTIAL EXFILTRATION",
        )
    ):
        return FailureClass.SECURITY_INCIDENT
    if any(token in value for token in ("401", "INVALID_API_KEY", "AUTHENTICATION", "CREDENTIAL")):
        if "GITHUB" in value:
            return FailureClass.GITHUB_AUTH_ERROR
        if "LINEAR" in value:
            return FailureClass.LINEAR_AUTH_ERROR
        return FailureClass.PROVIDER_AUTH_ERROR
    if any(token in value for token in ("MODEL_NOT_FOUND", "MODEL UNAVAILABLE", "DEPRECATED MODEL")):
        return FailureClass.MODEL_UNAVAILABLE
    if any(token in value for token in ("CONTEXT_LENGTH", "CONTEXT LIMIT", "TOO MANY TOKENS")):
        return FailureClass.MODEL_CONTEXT_LIMIT
    if any(token in value for token in ("429", "RATE_LIMIT", "RATE LIMIT")):
        return FailureClass.PROVIDER_RATE_LIMIT
    if "GITHUB" in value and any(token in value for token in ("TIMEOUT", "UNAVAILABLE", " 5")):
        return FailureClass.GITHUB_UNAVAILABLE
    if "LINEAR" in value and any(token in value for token in ("TIMEOUT", "UNAVAILABLE", " 5")):
        return FailureClass.LINEAR_UNAVAILABLE
    if "RAG" in value and any(token in value for token in ("TIMEOUT", "UNAVAILABLE", "FAILED")):
        return FailureClass.RAG_UNAVAILABLE
    if any(token in value for token in ("503", "502", "504", "CONNECTION RESET", "PROVIDER UNAVAILABLE")):
        return FailureClass.PROVIDER_UNAVAILABLE
    if any(token in value for token in ("PROVIDER", "HTTPSTATUSERROR", "CONNECTERROR", "READTIMEOUT")):
        return FailureClass.TRANSIENT_PROVIDER_ERROR
    if any(token in value for token in ("OUT OF MEMORY", "OOM", "EXITED 137")):
        return FailureClass.WORKER_OOM
    if any(token in value for token in ("TIMED_OUT", "WORKER TIMED OUT")):
        return FailureClass.WORKER_TIMEOUT
    if any(token in value for token in ("WORKER_CRASH", "WORKER EXITED", "CONTAINER EXIT")):
        return FailureClass.WORKER_CRASH
    if any(
        token in value
        for token in ("POLICY", "DENIED", "FORBIDDEN", "BUDGET EXHAUSTED")
    ):
        return FailureClass.POLICY_DENIED
    if any(token in value for token in ("PROTOCOL", "SCHEMA_VALIDATION", "INVALID WORKER RESULT")):
        return FailureClass.MODEL_PROTOCOL_ERROR
    if any(token in value for token in ("TEST_FAILED", "VALIDATION")):
        return FailureClass.VALIDATION_FAILURE
    if any(token in value for token in ("ARCHITECT", "REPLAN", "PLAN_MISMATCH")):
        return FailureClass.ARCHITECTURAL_FAILURE
    if any(token in value for token in ("AMBIGU", "NEEDS_CONTEXT")):
        return FailureClass.REQUIREMENT_AMBIGUITY
    if "NO_PROGRESS" in value:
        return FailureClass.NO_PROGRESS
    if any(token in value for token in ("WAIT", "PENDING_EXTERNAL")):
        return FailureClass.EXTERNAL_WAIT
    if "TOOL_INPUT" in value:
        return FailureClass.TOOL_INPUT_ERROR
    if "IMPLEMENTATION" in value:
        return FailureClass.IMPLEMENTATION_FAILURE
    return FailureClass.UNKNOWN_SYSTEM_ERROR
