import uuid
from dataclasses import dataclass

ROLE_CATEGORIES = frozenset(
    {"INTAKE", "PLANNING", "EXECUTION", "REVIEW", "COORDINATION", "SPECIALIST", "CUSTOM"}
)
ROLE_CAPABILITIES = frozenset(
    {
        "CAN_PLAN",
        "CAN_REPLAN",
        "CAN_IMPLEMENT",
        "CAN_REVIEW",
        "CAN_CLASSIFY_EXTERNAL_EVENT",
        "CAN_PRODUCE_FINDINGS",
        "CAN_RUN_VALIDATION",
    }
)
ROLE_PERMISSIONS = frozenset(
    {
        "READ_REPOSITORY",
        "WRITE_REPOSITORY",
        "READ_DIFF",
        "CREATE_FILES",
        "DELETE_FILES",
        "RUN_COMMANDS",
        "RUN_TESTS",
        "RUN_BUILD",
        "RUN_LINTER",
        "INSTALL_DEPENDENCIES",
        "CREATE_COMMIT",
        "CREATE_BRANCH",
        "GIT_STATUS",
        "GIT_DIFF",
        "PUSH_BRANCH",
        "PUSH_TASK_BRANCH",
        "READ_PR",
        "CREATE_PR",
        "UPDATE_PR",
        "COMMENT_PR",
        "READ_REVIEWS",
        "READ_CI",
        "MERGE_PR",
        "READ_TASKS",
        "READ_TASK",
        "UPDATE_TASKS",
        "UPDATE_TASK",
        "COMMENT_TASK",
        "CHANGE_TASK_STATUS",
        "READ_RAG",
        "WRITE_RAG",
        "UPLOAD_KNOWLEDGE",
        "ATTACH_KNOWLEDGE",
        "NETWORK_PACKAGE_REGISTRIES",
        "NETWORK_APPROVED_HOSTS",
        "NETWORK_UNRESTRICTED",
    }
)


@dataclass(frozen=True, slots=True)
class Role:
    id: uuid.UUID
    name: str
    category: str
    system_instructions: str
    capabilities: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    allowed_results: tuple[str, ...] = ()
    enabled: bool = True
    version: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Role name cannot be blank")
        if self.category not in ROLE_CATEGORIES:
            raise ValueError("Unsupported role category")
        if set(self.capabilities) - ROLE_CAPABILITIES:
            raise ValueError("Role contains unsupported capabilities")
        if set(self.permissions) - ROLE_PERMISSIONS:
            raise ValueError("Role contains unsupported permissions")
        if "CAN_IMPLEMENT" in self.capabilities and "WRITE_REPOSITORY" not in self.permissions:
            raise ValueError("Implementation roles require WRITE_REPOSITORY")
