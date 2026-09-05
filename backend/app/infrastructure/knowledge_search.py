import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.knowledge_search import (
    KnowledgeResult,
    SearchIndexNotReady,
    SearchRepositoryNotFound,
)
from app.db.models import IndexStatus, Repository
from app.infrastructure.indexing import semantic_search


class SqlAlchemyKnowledgeSearchWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self, repository_id: uuid.UUID, query: str, limit: int
    ) -> list[KnowledgeResult]:
        repository = await self._session.get(Repository, repository_id)
        if repository is None:
            raise SearchRepositoryNotFound("Repository not found")
        if repository.index_status != IndexStatus.READY:
            raise SearchIndexNotReady("Repository index is not ready")
        results = await semantic_search(self._session, repository_id, query, limit)
        return [
            KnowledgeResult(
                str(item["file_path"]),
                int(item["chunk_index"]),
                str(item["content"]),
                str(item["commit_sha"]),
                float(item["score"]),
            )
            for item in results
        ]
