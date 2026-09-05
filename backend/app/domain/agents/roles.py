from enum import StrEnum


class AgentRole(StrEnum):
    INTAKE = "INTAKE"
    THINKER = "THINKER"
    EXECUTOR = "EXECUTOR"
    REVIEWER = "REVIEWER"
