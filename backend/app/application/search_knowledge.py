import uuid

from app.application.ports.knowledge_search import KnowledgeResult, KnowledgeSearchWorkflow


class SearchKnowledge:
    def __init__(self, workflow: KnowledgeSearchWorkflow) -> None:
        self._workflow = workflow

    async def execute(
        self, repository_id: uuid.UUID, query: str, limit: int
    ) -> list[KnowledgeResult]:
        return await self._workflow.search(repository_id, query, min(max(limit, 1), 20))
