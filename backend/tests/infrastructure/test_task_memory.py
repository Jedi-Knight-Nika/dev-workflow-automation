from app.domain.memory import MemorySnapshot, checkpoint_payload, render_memory
from app.domain.operational_states import JobRole


def test_role_memory_views_do_not_dump_irrelevant_history() -> None:
    memory = MemorySnapshot(
        goal="Fix allocation",
        known_facts=("Fact",),
        decisions=("Decision",),
        rejected_approaches=({"approach": "Mutation", "reason": "Audit"},),
        important_files=("billing.py",),
        open_finding_ids=("finding-1",),
    )

    thinker = render_memory(memory, JobRole.THINKER)
    executor = render_memory(memory, JobRole.EXECUTOR)
    reviewer = render_memory(memory, JobRole.REVIEWER)

    assert thinker["rejected_approaches"]
    assert executor["decisions"] == ["Decision"]
    assert "rejected_approaches" not in executor
    assert "decisions" not in reviewer


def test_checkpoint_extracts_structured_deterministic_fields() -> None:
    payload = checkpoint_payload(
        JobRole.THINKER,
        {
            "targets": ["src/service.py"],
            "constraints": ["Preserve history"],
            "questions": ["Legacy behavior?"],
        },
    )

    assert payload["important_files"] == ["src/service.py"]
    assert payload["decisions"] == ["Preserve history"]
