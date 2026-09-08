def semantic_status(status: str, stage: str) -> str:
    """Tracker semantics never equate cancellation or suspension with delivery."""
    if status in {"MERGED", "CANCELLED", "PAUSED", "WAITING_HUMAN", "FAILED"}:
        return {
            "MERGED": "done",
            "CANCELLED": "cancelled",
            "PAUSED": "paused",
            "WAITING_HUMAN": "blocked",
            "FAILED": "blocked",
        }[status]
    if stage in {"REVIEWING", "MERGING"}:
        return "in_review"
    return "todo" if stage == "INTAKE" else "in_progress"
