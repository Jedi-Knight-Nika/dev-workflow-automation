"""Canonical handoff state independent of any model's wire encoding."""

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID


@dataclass(frozen=True)
class AgentEnvelope:
    version: int
    type: Literal["work", "repair", "result"]
    task_id: UUID
    requirement_revision: int
    current_sha: str | None
    payload: dict[str, Any]
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.version) is not int
            or self.version != 1
            or self.type not in {"work", "repair", "result"}
        ):
            raise ValueError("Unsupported agent protocol version or packet type")
        if (
            type(self.requirement_revision) is not int
            or self.requirement_revision < 1
            or len(self.evidence_refs) > 20
            or not isinstance(self.task_id, UUID)
            or (
                self.current_sha is not None
                and (not isinstance(self.current_sha, str) or len(self.current_sha) > 64)
            )
            or any(not isinstance(ref, str) or len(ref) > 500 for ref in self.evidence_refs)
        ):
            raise ValueError("Invalid handoff revision or evidence references")
        if self.type in {"work", "repair"} and not str(self.payload.get("request") or "").strip():
            raise ValueError("Work and repair packets require an explicit request")
