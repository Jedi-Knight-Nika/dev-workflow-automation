import re
import shlex
from dataclasses import dataclass, field
from enum import StrEnum


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_HUMAN = "REQUIRE_HUMAN"


class ExecutionMode(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    AUTONOMOUS = "AUTONOMOUS"
    CUSTOM = "CUSTOM"


CAPABILITY_CATALOG = frozenset(
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
        "GIT_STATUS",
        "GIT_DIFF",
        "CREATE_COMMIT",
        "CREATE_BRANCH",
        "PUSH_TASK_BRANCH",
        "READ_PR",
        "CREATE_PR",
        "UPDATE_PR",
        "COMMENT_PR",
        "READ_REVIEWS",
        "READ_CI",
        "MERGE_PR",
        "READ_TASK",
        "UPDATE_TASK",
        "COMMENT_TASK",
        "CHANGE_TASK_STATUS",
        "READ_RAG",
        "WRITE_RAG",
        "ATTACH_KNOWLEDGE",
        "NETWORK_PACKAGE_REGISTRIES",
        "NETWORK_APPROVED_HOSTS",
        "NETWORK_UNRESTRICTED",
    }
)
HARD_DENIED_COMMANDS = frozenset(
    {
        "sudo",
        "su",
        "mount",
        "umount",
        "reboot",
        "shutdown",
        "systemctl",
        "launchctl",
        "runas",
        "docker",
        "kubectl",
    }
)
MODERATE_CAPABILITIES = {
    "INSTALL_DEPENDENCIES",
    "CREATE_COMMIT",
    "PUSH_TASK_BRANCH",
    "CREATE_PR",
    "UPDATE_PR",
}


@dataclass(frozen=True, slots=True)
class TeamExecutionPolicy:
    mode: ExecutionMode = ExecutionMode.AUTONOMOUS
    settings: dict[str, Decision] = field(default_factory=dict)
    approved_hosts: tuple[str, ...] = ()
    max_command_timeout_seconds: int = 1200
    max_output_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        unknown = set(self.settings) - CAPABILITY_CATALOG
        if unknown:
            raise ValueError(f"Unknown capabilities: {', '.join(sorted(unknown))}")
        if not 10 <= self.max_command_timeout_seconds <= 7200:
            raise ValueError("Command timeout must be between 10 and 7200 seconds")
        if not 1024 <= self.max_output_bytes <= 5_000_000:
            raise ValueError("Maximum output must be between 1024 and 5000000 bytes")

    def outcome(self, capability: str) -> Decision:
        if capability == "MERGE_PR":
            if self.settings.get(capability) == Decision.DENY:
                return Decision.DENY
            return Decision.REQUIRE_HUMAN
        if capability == "NETWORK_UNRESTRICTED":
            return Decision.DENY
        if capability in self.settings:
            return self.settings[capability]
        if self.mode == ExecutionMode.CONSERVATIVE and capability in MODERATE_CAPABILITIES | {
            "WRITE_REPOSITORY",
            "CREATE_FILES",
            "DELETE_FILES",
        }:
            return Decision.REQUIRE_HUMAN
        return Decision.ALLOW


@dataclass(frozen=True, slots=True)
class ActionRequest:
    tool: str
    action: str
    required_permission: str
    effective_permissions: frozenset[str]
    command: tuple[str, ...] = ()
    target_branch: str | None = None
    task_branch: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: Decision
    policy_rule: str
    reason: str
    effective_permission: str | None = None


def _command_name(word: str) -> str:
    name = word.casefold().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name.removesuffix(".exe").removesuffix(".cmd").removesuffix(".bat")


def evaluate(policy: TeamExecutionPolicy, request: ActionRequest) -> PolicyDecision:
    if request.required_permission not in CAPABILITY_CATALOG:
        return PolicyDecision(Decision.DENY, "platform.capability.unknown", "Unknown capability")
    if request.required_permission not in request.effective_permissions:
        return PolicyDecision(
            Decision.DENY,
            "role.permission.missing",
            f"Effective Role configuration does not grant {request.required_permission}",
        )
    if request.command:
        command_words = {
            _command_name(word)
            for argument in request.command
            for word in re.findall(r"[A-Za-z0-9_.\\/:-]+", argument)
        }
        forbidden = sorted(command_words & HARD_DENIED_COMMANDS)
        if forbidden:
            return PolicyDecision(
                Decision.DENY,
                "platform.command.forbidden",
                f"{forbidden[0]} is hard-denied",
            )
        rendered = " ".join(shlex.quote(part) for part in request.command).casefold()
        if "/var/run/docker.sock" in rendered or "\\.\\pipe\\docker_engine" in rendered:
            return PolicyDecision(
                Decision.DENY,
                "platform.docker_socket.forbidden",
                "Docker daemon access is forbidden",
            )
    if request.action == "push" and (
        not request.task_branch or request.target_branch != request.task_branch
    ):
        return PolicyDecision(
            Decision.DENY, "git.task_branch.only", "Only the assigned task branch may be pushed"
        )
    outcome = policy.outcome(request.required_permission)
    return PolicyDecision(
        outcome,
        f"team.{policy.mode.value.casefold()}.{request.required_permission.casefold()}",
        "Allowed by effective policy"
        if outcome == Decision.ALLOW
        else "Team policy requires this decision",
        request.required_permission,
    )
