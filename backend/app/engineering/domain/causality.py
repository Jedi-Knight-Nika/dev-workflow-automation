"""Optional execution audit references; they do not authorize a transition."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class TransitionCause:
    action_id: UUID | None = None
    job_id: UUID | None = None
    review_ids: tuple[UUID, ...] = ()

    def facts(self) -> dict[str, Any]:
        return {
            **({"action_id": str(self.action_id)} if self.action_id else {}),
            **({"job_id": str(self.job_id)} if self.job_id else {}),
            **(
                {"review_cycle_ids": [str(id) for id in self.review_ids[:50]]}
                if self.review_ids
                else {}
            ),
            **({"omitted_causes": len(self.review_ids) - 50} if len(self.review_ids) > 50 else {}),
        }
