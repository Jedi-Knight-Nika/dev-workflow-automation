import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SupervisorCheckpoint(BaseModel):
    """Small runtime response; no repeated task brief or self-scored confidence."""

    model_config = ConfigDict(extra="forbid")
    directive: Literal["CONTINUE", "NARROW_SCOPE", "EDIT_NOW", "INFRA_PROBLEM", "ESCALATE"]
    message: str = Field(max_length=600)

    def annotations(self) -> "SupervisorDecision":
        # Keep the persisted/transport contract compatible with initial decisions.
        action = (
            "CONTINUE"
            if self.directive == "CONTINUE"
            else "STOP"
            if self.directive in {"INFRA_PROBLEM", "ESCALATE"}
            else "NUDGE"
        )
        return SupervisorDecision(
            action=action,
            task_class="STANDARD",
            confidence=0,
            assessment=self.directive,
            execution_brief=self.message,
            acceptance_criteria=[],
            unresolved_items=[],
            physical_object="",
            operations=[],
            preserve=[],
            do_not_assume=[],
        )


class SupervisorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "DELEGATE_IMPLEMENTATION", "DELEGATE_REPAIR", "WAIT_HUMAN", "CONTINUE", "NUDGE", "STOP"
    ]
    task_class: Literal["TINY", "STANDARD", "COMPLEX", "HIGH_RISK"]
    confidence: float = Field(ge=0, le=1)
    assessment: str = Field(max_length=1000)
    execution_brief: str = Field(max_length=3000)
    acceptance_criteria: list[str] = Field(max_length=8)
    unresolved_items: list[str] = Field(max_length=8)
    physical_object: str = Field(max_length=300)
    operations: list[str] = Field(max_length=6)
    preserve: list[str] = Field(max_length=6)
    do_not_assume: list[str] = Field(max_length=6)
    target_paths: list[str] = Field(default_factory=list, max_length=3)
    execution_mode: Literal["FAST_PATCH", "STRUCTURED_MULTI_PATCH", "BOUNDED_AGENTIC"] = (
        "FAST_PATCH"
    )

    def developer_guidance(self) -> str:
        return (
            "\nAdvisory Supervisor annotations. The ORIGINAL USER TASK above is authoritative. "
            "Reject annotations that change the object or requested behavior; do not substitute this interpretation for the task:\n"
            + json.dumps(self.model_dump(), ensure_ascii=False)
        )
