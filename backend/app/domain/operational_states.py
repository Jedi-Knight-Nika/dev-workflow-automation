from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    RETRY_WAIT = "RETRY_WAIT"


class JobRole(StrEnum):
    INTAKE = "INTAKE"
    THINKER = "THINKER"
    EXECUTOR = "EXECUTOR"
    REVIEWER = "REVIEWER"


class IntegrationStatus(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONFIGURED = "CONFIGURED"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class IndexStatus(StrEnum):
    NOT_INDEXED = "NOT_INDEXED"
    QUEUED = "QUEUED"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
