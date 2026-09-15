"""Validate provider payloads before constructing a semantic domain decision."""

from dataclasses import asdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.coordinator.domain.protocol import Checkpoint, Decision, Directive


class CheckpointSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(max_length=1200)
    invariants: list[str] = Field(max_length=8)
    open_questions: list[str] = Field(max_length=5)


class DecisionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    action: Directive
    message: str = Field(max_length=3000)
    engineering_request: str = Field(max_length=8000)
    reason: str = Field(min_length=1, max_length=800)
    choices: list[str] = Field(max_length=4)
    read_tools: list[
        Literal[
            "READ_DISCUSSION",
            "READ_PR",
            "READ_REVIEWS",
            "READ_REVIEW_DELTA",
            "READ_CHECKS",
            "READ_TASK",
        ]
    ] = Field(max_length=2)
    checkpoint: CheckpointSchema

    @model_validator(mode="after")
    def coherent(self) -> "DecisionSchema":
        if (
            self.action in {Directive.ASK_HUMAN, Directive.REPLY, Directive.UPDATE_SUMMARY}
            and not self.message.strip()
        ):
            raise ValueError("A reply or question needs message text")
        if (
            self.action in {Directive.IMPLEMENT, Directive.REPAIR}
            and not self.engineering_request.strip()
        ):
            raise ValueError("Engineering work needs an explicit request")
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("Choices must be unique")
        if any(not item.strip() or len(item) > 300 for item in self.choices):
            raise ValueError("Choices must contain 1–300 characters")
        if any(
            len(item) > 600
            for item in [*self.checkpoint.invariants, *self.checkpoint.open_questions]
        ):
            raise ValueError("Checkpoint entries exceed their bounds")
        return self


def decision_payload(decision: Decision) -> dict[str, Any]:
    return DecisionSchema.model_validate(asdict(decision)).model_dump(mode="json")


def parse_decision(payload: Any) -> Decision:
    value = DecisionSchema.model_validate(payload)
    return Decision(
        version=value.version,
        action=value.action,
        message=value.message,
        engineering_request=value.engineering_request,
        reason=value.reason,
        choices=tuple(value.choices),
        read_tools=tuple(value.read_tools),
        checkpoint=Checkpoint(
            value.checkpoint.goal,
            tuple(value.checkpoint.invariants),
            tuple(value.checkpoint.open_questions),
        ),
    )
