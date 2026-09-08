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
