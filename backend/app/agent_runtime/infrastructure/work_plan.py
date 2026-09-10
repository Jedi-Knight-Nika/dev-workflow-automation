"""Validated model-facing work artifacts. No model confidence authorizes execution."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionMode(StrEnum):
    FAST_PATCH = "FAST_PATCH"
    STRUCTURED_MULTI_PATCH = "STRUCTURED_MULTI_PATCH"
    BOUNDED_AGENTIC = "BOUNDED_AGENTIC"


class WorkUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_-]+$")
    objective: str = Field(min_length=1, max_length=1200)
    candidate_files: list[str] = Field(min_length=1, max_length=3)
    new_files: list[str] = Field(default_factory=list, max_length=2)
    depends_on: list[str] = Field(max_length=5)
    acceptance_checks: list[str] = Field(max_length=6)
    exported_contracts: list[str] = Field(max_length=6)

    @model_validator(mode="after")
    def bounded_files(self) -> "WorkUnit":
        paths = self.candidate_files + self.new_files
        if len(set(paths)) != len(paths) or len(paths) > 3:
            raise ValueError("A work unit must contain at most three distinct existing/new files")
        return self


class WorkGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str = Field(min_length=1, max_length=1200)
    integration_invariants: list[str] = Field(max_length=8)
    units: list[WorkUnit] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def valid_graph(self) -> "WorkGraph":
        ids = [unit.id for unit in self.units]
        if len(ids) != len(set(ids)):
            raise ValueError("Work unit IDs must be unique")
        self.ordered_units()
        return self

    def ordered_units(self) -> list[WorkUnit]:
        ordered: list[WorkUnit] = []
        pending = list(self.units)
        while pending:
            completed = {unit.id for unit in ordered}
            ready = next((unit for unit in pending if set(unit.depends_on) <= completed), None)
            if ready is None:
                raise ValueError("Work plan has a cycle or unknown dependency")
            ordered.append(ready)
            pending.remove(ready)
        return ordered


class PlanProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graph: WorkGraph | None
    blocked_reason: str = Field(max_length=1000)


class InvestigationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_cause: str = Field(max_length=1600)
    relevant_files: list[str] = Field(max_length=18)
    evidence: list[str] = Field(max_length=8)
    uncertainty: list[str] = Field(max_length=6)
    # One batch of reads, not a general shell or a coding tool loop.
    inspect_paths: list[str] = Field(max_length=3)
    search_query: str = Field(default="", max_length=600)
    ready: bool
