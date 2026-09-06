import uuid

import pytest

from app.application.ports.knowledge_search import KnowledgeResult
from app.application.search_knowledge import SearchKnowledge


class FakeSearch:
    def __init__(self) -> None:
        self.limit = 0

    async def search(
        self, repository_id: uuid.UUID, query: str, limit: int
    ) -> list[KnowledgeResult]:
        self.limit = limit
        return [KnowledgeResult("a.py", 0, query, "sha", 0.9)]


@pytest.mark.asyncio
async def test_knowledge_search_clamps_limit_and_delegates() -> None:
    workflow = FakeSearch()
    result = await SearchKnowledge(workflow).execute(uuid.uuid4(), "needle", 99)
    assert workflow.limit == 20
    assert result[0].content == "needle"
