"""A human message and its interpretation are evidence, not merge authority."""

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewMessage:
    source: str
    source_id: str
    actor_id: str
    head_sha: str
    body: str
    updated_at: str

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()


@dataclass(frozen=True)
class ReviewedMessage:
    key: str
    actor_id: str
    head_sha: str
    digest: str
    updated_at: str
    decision: str

    def matches(self, message: ReviewMessage) -> bool:
        return (
            self.key == message.key
            and self.actor_id == message.actor_id
            and self.head_sha == message.head_sha
            and self.digest == message.digest
            and self.updated_at == message.updated_at
        )


def resolved_duplicate(
    message: ReviewMessage,
    saved: ReviewedMessage | None,
    live_messages: tuple[ReviewMessage, ...],
    reviewed: tuple[ReviewedMessage, ...],
) -> bool:
    """An unresolved duplicate can reuse an unchanged, newer approval on this SHA.

    Never erase real feedback or trust a deleted/edited approval from saved state.
    """
    if saved is None or saved.decision != "NEEDS_CLASSIFICATION":
        return False
    return any(
        newer.key != message.key
        and newer.source == message.source
        and newer.actor_id == message.actor_id
        and newer.head_sha == message.head_sha
        and newer.body == message.body
        and newer.updated_at > message.updated_at
        and any(r.decision == "APPROVAL_INTERPRETED" and r.matches(newer) for r in reviewed)
        for newer in live_messages
    )
