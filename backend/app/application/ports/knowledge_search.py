import uuid
from dataclasses import dataclass
from typing import Protocol


class SearchRepositoryNotFound(Exception):
    pass


class SearchIndexNotReady(Exception):
    pass


@dataclass(frozen=True, slots=True)
class KnowledgeResult:
    file_path: str
    chunk_index: int
    content: str
    commit_sha: str
    score: float


class KnowledgeSearchWorkflow(Protocol):
    async def search(
        self, repository_id: uuid.UUID, query: str, limit: int
    ) -> list[KnowledgeResult]: ...
