from typing import NoReturn

from app.agent_runtime.application.harness import TurnReceipt
from app.engineering.application.jobs import PhaseBlocked
from app.engineering.domain.lifecycle import WaitReason


def block_failed_turn(receipt: TurnReceipt, harness: str) -> NoReturn:
    if receipt.failure_code in {
        "TURN_INPUT_LIMIT",
        "CONTEXT_HARD_LIMIT",
        "EXPLORATION_LIMIT",
    }:
        raise PhaseBlocked(
            WaitReason.TOKEN_LIMIT,
            f"Developer interrupted: {receipt.failure_code}; worktree and session retained",
        )
    if receipt.failure_code == "SUPERVISOR_STOP":
        raise PhaseBlocked(
            WaitReason.RUNTIME_FAILURE,
            "Supervisor stopped this attempt; inspect SUPERVISOR_DECIDED evidence",
        )
    if receipt.failure_code in {
        "NO_PROGRESS",
        "REPEATED_TOOL_LOOP",
        "REPEATED_READ_LOOP",
    }:
        raise PhaseBlocked(
            WaitReason.NO_PROGRESS,
            f"Developer interrupted: {receipt.failure_code}; evidence retained",
        )
    if receipt.failure_code == "TURN_BUDGET_EXHAUSTED":
        raise PhaseBlocked(
            WaitReason.BUDGET_EXHAUSTED,
            "Developer reached its reserved USD allowance",
        )
    if harness == "patch":
        reason = {
            "BUDGET_LIMIT": WaitReason.BUDGET_EXHAUSTED,
            "PATCH_LIMIT": WaitReason.NO_PROGRESS,
            "PATCH_TOOL_FAILURE": WaitReason.RUNTIME_FAILURE,
            "PATCH_FAILED": WaitReason.RUNTIME_FAILURE,
            "USAGE_INCOMPLETE": WaitReason.RUNTIME_FAILURE,
            "RESPONSE_INCOMPLETE": WaitReason.RUNTIME_FAILURE,
            "TURN_INPUT_LIMIT": WaitReason.NO_PROGRESS,
            "PATCH_ALREADY_ATTEMPTED": WaitReason.NO_PROGRESS,
        }.get(receipt.failure_code or "", WaitReason.MISSING_REQUIREMENT)
        raise PhaseBlocked(reason, f"{receipt.failure_code}: {receipt.summary}"[:1000])
    if receipt.failure_code == "PROVIDER_AUTHENTICATION_FAILED":
        raise PhaseBlocked(
            WaitReason.MISSING_CONFIGURATION,
            "Native provider authentication failed; verify the integration "
            "and runner login before resuming this session",
        )
    raise PhaseBlocked(
        WaitReason.MISSING_REQUIREMENT,
        "Developer did not finish; inspect its preserved session"
        + (f" ({receipt.failure_code})" if receipt.failure_code else ""),
    )
