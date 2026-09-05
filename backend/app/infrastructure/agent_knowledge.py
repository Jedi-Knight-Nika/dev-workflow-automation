import uuid

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentKnowledgeChunk, AgentKnowledgeSource, JobRole
from app.domain.indexing import chunk_source, vector_literal
from app.infrastructure.indexing import embedding_client


async def list_agent_knowledge(session: AsyncSession, role: JobRole) -> list[AgentKnowledgeSource]:
    return list(
        (
            await session.scalars(
                select(AgentKnowledgeSource)
                .where(AgentKnowledgeSource.role == role)
                .order_by(AgentKnowledgeSource.created_at.desc())
            )
        ).all()
    )


async def create_agent_knowledge(
    session: AsyncSession, role: JobRole, title: str, content: str
) -> AgentKnowledgeSource:
    chunks = chunk_source(f"manual/{title}.txt", content)
    client = await embedding_client(session)
    embeddings = await client.embed([chunk.content for chunk in chunks])
    if len(embeddings) != len(chunks):
        raise RuntimeError("Embedding provider returned an incomplete batch")
    source = AgentKnowledgeSource(
        role=role, title=title.strip(), content=content, chunk_count=len(chunks)
    )
    session.add(source)
    await session.flush()
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        await session.execute(
            text(
                """INSERT INTO agent_knowledge_chunks
                (id, source_id, role, chunk_index, content, embedding)
                VALUES (:id, :source_id, CAST(:role AS jobrole), :chunk_index, :content,
                        CAST(:embedding AS vector))"""
            ),
            {
                "id": uuid.uuid4(),
                "source_id": source.id,
                "role": role.value,
                "chunk_index": chunk.index,
                "content": chunk.content,
                "embedding": vector_literal(embedding),
            },
        )
    await session.commit()
    await session.refresh(source)
    return source


async def delete_agent_knowledge(
    session: AsyncSession, role: JobRole, source_id: uuid.UUID
) -> bool:
    source = await session.get(AgentKnowledgeSource, source_id)
    if source is None or source.role != role:
        return False
    await session.execute(delete(AgentKnowledgeSource).where(AgentKnowledgeSource.id == source_id))
    await session.commit()
    return True


async def search_agent_knowledge(
    session: AsyncSession, role: JobRole, query: str, limit: int = 6
) -> list[dict[str, object]]:
    chunk_count = await session.scalar(
        select(func.count())
        .select_from(AgentKnowledgeChunk)
        .where(AgentKnowledgeChunk.role == role)
    )
    if not chunk_count:
        return []
    client = await embedding_client(session)
    embedding = (await client.embed([query]))[0]
    rows = (
        await session.execute(
            text(
                """SELECT source_id, chunk_index, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
                   FROM agent_knowledge_chunks WHERE role = CAST(:role AS jobrole)
                   ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"""
            ),
            {"role": role.value, "embedding": vector_literal(embedding), "limit": limit},
        )
    ).mappings()
    return [dict(row) for row in rows]
