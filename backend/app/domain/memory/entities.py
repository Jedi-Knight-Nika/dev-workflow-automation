from dataclasses import dataclass
from typing import Any

from app.domain.operational_states import JobRole


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    goal: str
    known_facts: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    rejected_approaches: tuple[dict[str, str], ...] = ()
    invariants: tuple[str, ...] = ()
    important_files: tuple[str, ...] = ()
    important_symbols: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    open_finding_ids: tuple[str, ...] = ()
    resolved_finding_summaries: tuple[str, ...] = ()
    current_plan_job_id: str | None = None
    current_sha: str | None = None
    version: int = 1


def render_memory(memory: MemorySnapshot, role: JobRole) -> dict[str, Any]:
    common: dict[str, Any] = {
        "goal": memory.goal,
        "invariants": list(memory.invariants),
        "open_questions": list(memory.open_questions),
        "current_sha": memory.current_sha,
        "memory_version": memory.version,
    }
    if role == JobRole.INTAKE:
        common["known_facts"] = list(memory.known_facts)
    elif role == JobRole.THINKER:
        common.update(
            known_facts=list(memory.known_facts),
            decisions=list(memory.decisions),
            rejected_approaches=list(memory.rejected_approaches),
            important_files=list(memory.important_files),
            important_symbols=list(memory.important_symbols),
            open_finding_ids=list(memory.open_finding_ids),
        )
    elif role == JobRole.EXECUTOR:
        common.update(
            decisions=list(memory.decisions),
            important_files=list(memory.important_files),
            important_symbols=list(memory.important_symbols),
            open_finding_ids=list(memory.open_finding_ids),
            current_plan_job_id=memory.current_plan_job_id,
        )
    else:
        common.update(
            known_facts=list(memory.known_facts),
            open_finding_ids=list(memory.open_finding_ids),
        )
    return common


def checkpoint_payload(role: JobRole, result: dict[str, Any]) -> dict[str, Any]:
    if role == JobRole.THINKER:
        return {
            "decisions": _strings(result.get("constraints")),
            "important_files": _strings(result.get("targets")),
            "open_questions": _strings(result.get("questions")),
            "risks": _strings(result.get("risks")),
            "acceptance_criteria": _strings(result.get("acceptance_criteria")),
        }
    if role == JobRole.EXECUTOR:
        return {
            "important_files": _strings(result.get("changed_files")),
            "tests": result.get("checks", []),
            "plan_mismatch": result.get("plan_mismatch"),
        }
    if role == JobRole.REVIEWER:
        return {"findings": result.get("findings", []), "outcome": result.get("result")}
    return {
        "interpreted_goal": result.get("summary"),
        "event_type": result.get("event_type"),
    }


def _strings(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []
