from enum import StrEnum


class FailureClass(StrEnum):
    TRANSIENT_INFRA = "TRANSIENT_INFRA"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_AUTH = "PROVIDER_AUTH"
    MODEL_PROTOCOL_ERROR = "MODEL_PROTOCOL_ERROR"
    TOOL_INPUT_ERROR = "TOOL_INPUT_ERROR"
    IMPLEMENTATION_FAILURE = "IMPLEMENTATION_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    ARCHITECTURAL_FAILURE = "ARCHITECTURAL_FAILURE"
    REQUIREMENT_AMBIGUITY = "REQUIREMENT_AMBIGUITY"
    POLICY_DENIED = "POLICY_DENIED"
    NO_PROGRESS = "NO_PROGRESS"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    EXTERNAL_WAIT = "EXTERNAL_WAIT"


def classify_failure(*, code: str | None, outcome: str | None) -> FailureClass:
    value = (code or outcome or "").upper()
    if any(token in value for token in ("429", "RATE_LIMIT")):
        return FailureClass.PROVIDER_RATE_LIMIT
    if any(token in value for token in ("AUTH", "CREDENTIAL")):
        return FailureClass.PROVIDER_AUTH
    if any(token in value for token in ("POLICY", "DENIED", "FORBIDDEN")):
        return FailureClass.POLICY_DENIED
    if any(token in value for token in ("SECURITY", "SANDBOX_ESCAPE")):
        return FailureClass.SECURITY_INCIDENT
    if any(token in value for token in ("PROTOCOL", "SCHEMA_VALIDATION")):
        return FailureClass.MODEL_PROTOCOL_ERROR
    if any(token in value for token in ("TIMEOUT", "UNAVAILABLE", "CONNECTION", "WORKER_CRASH")):
        return FailureClass.TRANSIENT_INFRA
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
    return FailureClass.IMPLEMENTATION_FAILURE
