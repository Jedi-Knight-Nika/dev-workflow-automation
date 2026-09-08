from enum import StrEnum


class LifecycleAction(StrEnum):
    PAUSE = "PAUSE"
    CANCEL = "CANCEL"
    TAKEOVER = "TAKEOVER"
    RESUME = "RESUME"
    ARCHIVE = "ARCHIVE"
