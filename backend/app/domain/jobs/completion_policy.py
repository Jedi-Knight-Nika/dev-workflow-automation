from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CompletionDirective(StrEnum):
    INTAKE_NEEDS_HUMAN = "INTAKE_NEEDS_HUMAN"
    INTAKE_INFORMATIONAL = "INTAKE_INFORMATIONAL"
    INTAKE_REPAIR = "INTAKE_REPAIR"
    INTAKE_REPLAN = "INTAKE_REPLAN"
    INTAKE_PLAN = "INTAKE_PLAN"
    THINKER_EXECUTE = "THINKER_EXECUTE"
    THINKER_NEEDS_CONTEXT = "THINKER_NEEDS_CONTEXT"
    THINKER_NEEDS_HUMAN = "THINKER_NEEDS_HUMAN"
    EXECUTOR_REVIEW = "EXECUTOR_REVIEW"
    EXECUTOR_REPAIR = "EXECUTOR_REPAIR"
    EXECUTOR_REPLAN = "EXECUTOR_REPLAN"
    EXECUTOR_NEEDS_HUMAN = "EXECUTOR_NEEDS_HUMAN"
    REVIEW_PUBLISH = "REVIEW_PUBLISH"
    REVIEW_REPAIR = "REVIEW_REPAIR"
    REVIEW_REPLAN = "REVIEW_REPLAN"
    REVIEW_NEEDS_HUMAN = "REVIEW_NEEDS_HUMAN"


class JobExecutionState(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: int

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts

    def delay_seconds(self, attempt: int) -> int:
        return self.base_delay_seconds * (1 << max(attempt - 1, 0))


def success_directive(
    *,
    role: str,
    action: str,
    outcome: str | None,
    data: dict[str, Any],
    repeat_count: int = 0,
    max_same_finding_repeats: int = 2,
) -> CompletionDirective:
    if role == "INTAKE":
        if outcome != "EVENT_INTERPRETED" or data.get("actionability") == "NEEDS_HUMAN":
            return CompletionDirective.INTAKE_NEEDS_HUMAN
        if action != "INTERPRET_EXTERNAL_COMMENT":
            return CompletionDirective.INTAKE_PLAN
        if data.get("actionability") == "INFORMATIONAL":
            return CompletionDirective.INTAKE_INFORMATIONAL
        if data.get("event_type") == "REVIEW_FIX":
            return CompletionDirective.INTAKE_REPAIR
        return CompletionDirective.INTAKE_REPLAN
    if role == "THINKER":
        if outcome == "PLAN_READY":
            return CompletionDirective.THINKER_EXECUTE
        if outcome == "NEEDS_CONTEXT":
            return CompletionDirective.THINKER_NEEDS_CONTEXT
        return CompletionDirective.THINKER_NEEDS_HUMAN
    if role == "EXECUTOR":
        if outcome == "IMPLEMENTED":
            return CompletionDirective.EXECUTOR_REVIEW
        if outcome == "TEST_FAILED":
            return CompletionDirective.EXECUTOR_REPAIR
        if outcome in {"PLAN_MISMATCH", "NEEDS_REPLAN"}:
            return CompletionDirective.EXECUTOR_REPLAN
        return CompletionDirective.EXECUTOR_NEEDS_HUMAN
    if role == "REVIEWER":
        if outcome == "PASS":
            return CompletionDirective.REVIEW_PUBLISH
        if repeat_count >= max_same_finding_repeats:
            return CompletionDirective.REVIEW_NEEDS_HUMAN
        if outcome == "FAIL_ACTIONABLE":
            return CompletionDirective.REVIEW_REPAIR
        if outcome == "FAIL_ARCHITECTURAL":
            return CompletionDirective.REVIEW_REPLAN
        return CompletionDirective.REVIEW_NEEDS_HUMAN
    raise ValueError(f"Unsupported job role: {role}")
