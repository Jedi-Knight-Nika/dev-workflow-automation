import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IndexStatus, Integration, Repository
from app.domain.indexing import (
    SourceChunk,
    chunk_metadata,
    chunk_source,
    chunks_requiring_embeddings,
    parse_changed_paths,
    should_index_content,
    should_index_path,
    vector_literal,
)
from app.infrastructure.git.workspaces import prepare_repository_cache, run_git
from app.infrastructure.security.crypto import cipher
from app.providers.embeddings import OpenAIEmbeddings


async def scan_repository(
    cache: Path, revision: str, file_paths: list[str] | None = None
) -> list[SourceChunk]:
    files = file_paths
    if files is None:
        files = (await run_git("ls-tree", "-r", "--name-only", revision, cwd=cache)).splitlines()
    chunks: list[SourceChunk] = []
    for file_path in files:
        if not should_index_path(file_path):
            continue
        try:
            raw = await run_git("show", f"{revision}:{file_path}", cwd=cache)
        except RuntimeError:
            # The path may have been deleted between indexed revisions.
            continue
        if not should_index_content(raw):
            continue
        chunks.extend(chunk_source(file_path, raw))
    return chunks


async def changed_paths(cache: Path, old_revision: str, new_revision: str) -> list[str]:
    output = await run_git(
        "diff",
        "--name-only",
        "--no-renames",
        old_revision,
        new_revision,
        cwd=cache,
    )
    return parse_changed_paths(output)


async def embedding_client(session: AsyncSession) -> OpenAIEmbeddings:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "openai")
    )
    if integration is None or integration.encrypted_credentials is None:
        raise RuntimeError("Configure OpenAI before indexing")
    model = str(integration.configuration.get("embedding_model", "text-embedding-3-small"))
    return OpenAIEmbeddings(cipher.decrypt(integration.encrypted_credentials), model)


async def index_repository(session: AsyncSession, repository: Repository) -> int:
    repository.index_status = IndexStatus.INDEXING
    repository.index_error = None
    await session.commit()
    cache = await prepare_repository_cache(session, repository)
    if not repository.latest_sha:
        raise RuntimeError("Repository has no default-branch revision")
    revision = repository.latest_sha
    if repository.indexed_sha == revision:
        repository.index_status = IndexStatus.READY
        repository.indexed_at = datetime.now(UTC)
        await session.commit()
        return 0
    previous_revision = repository.indexed_sha
    incremental_paths: list[str] | None = None
    if previous_revision:
        try:
            incremental_paths = await changed_paths(cache, previous_revision, revision)
        except RuntimeError:
            # Force-pushes or pruned history fall back to a safe full rebuild.
            incremental_paths = None
    chunks = await scan_repository(cache, revision, incremental_paths)
    cached_embeddings: dict[tuple[str, str], str] = {}
    if incremental_paths is None:
        await session.execute(
            text("DELETE FROM knowledge_chunks WHERE repository_id = :repository_id"),
            {"repository_id": repository.id},
        )
    else:
        if incremental_paths:
            existing = (
                await session.execute(
                    text(
                        """SELECT file_path, content_hash, embedding::text AS embedding
                        FROM knowledge_chunks
                        WHERE repository_id = :repository_id AND file_path = ANY(:file_paths)"""
                    ),
                    {"repository_id": repository.id, "file_paths": incremental_paths},
                )
            ).mappings()
            cached_embeddings = {
                (str(row["file_path"]), str(row["content_hash"])): str(row["embedding"])
                for row in existing
                if row["embedding"] is not None
            }
            await session.execute(
                text(
                    """DELETE FROM knowledge_chunks
                    WHERE repository_id = :repository_id AND file_path = ANY(:file_paths)"""
                ),
                {"repository_id": repository.id, "file_paths": incremental_paths},
            )
        await session.execute(
            text(
                """UPDATE knowledge_chunks SET commit_sha = :revision
                WHERE repository_id = :repository_id"""
            ),
            {"repository_id": repository.id, "revision": revision},
        )
    client = (
        await embedding_client(session)
        if chunks_requiring_embeddings(chunks, cached_embeddings)
        else None
    )
    indexed_at = datetime.now(UTC)
    for offset in range(0, len(chunks), 64):
        batch = chunks[offset : offset + 64]
        missing = chunks_requiring_embeddings(batch, cached_embeddings)
        if missing and client is None:
            raise RuntimeError("Embedding provider is unavailable for new repository content")
        generated = await client.embed([chunk.content for chunk in missing]) if client else []
        if len(generated) != len(missing):
            raise RuntimeError("Embedding provider returned an incomplete batch")
        generated_embeddings = {
            (chunk.file_path, chunk.content_hash): vector_literal(embedding)
            for chunk, embedding in zip(missing, generated, strict=True)
        }
        for chunk in batch:
            embedding = (
                cached_embeddings.get((chunk.file_path, chunk.content_hash))
                or generated_embeddings[(chunk.file_path, chunk.content_hash)]
            )
            await session.execute(
                text(
                    """INSERT INTO knowledge_chunks
                    (id, repository_id, branch, commit_sha, file_path, chunk_index,
                     content, content_hash, metadata_json, embedding)
                    VALUES (:id, :repository_id, :branch, :commit_sha, :file_path, :chunk_index,
                     :content, :content_hash, CAST(:metadata_json AS jsonb), CAST(:embedding AS vector))"""
                ),
                {
                    "id": uuid.uuid4(),
                    "repository_id": repository.id,
                    "branch": repository.default_branch,
                    "commit_sha": revision,
                    "file_path": chunk.file_path,
                    "chunk_index": chunk.index,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                    "metadata_json": json.dumps(chunk_metadata(chunk, indexed_at)),
                    "embedding": embedding,
                },
            )
    repository.indexed_sha = revision
    repository.indexed_at = indexed_at
    repository.index_status = IndexStatus.READY
    await session.commit()
    return len(chunks)


async def process_queued_indexes(session: AsyncSession) -> int:
    repository = await session.scalar(
        select(Repository)
        .where(Repository.enabled.is_(True), Repository.index_status == IndexStatus.QUEUED)
        .order_by(Repository.updated_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if repository is None:
        return 0
    repository_id = repository.id
    try:
        await index_repository(session, repository)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        await session.rollback()
        repository = await session.get(Repository, repository_id)
        if repository:
            repository.index_status = IndexStatus.FAILED
            repository.index_error = str(exc)[:2000]
            await session.commit()
    return 1


async def semantic_search(
    session: AsyncSession, repository_id: uuid.UUID, query: str, limit: int = 8
) -> list[dict[str, Any]]:
    client = await embedding_client(session)
    embedding = (await client.embed([query]))[0]
    rows = (
        await session.execute(
            text(
                """SELECT file_path, chunk_index, content, commit_sha,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
                   FROM knowledge_chunks WHERE repository_id = :repository_id
                   ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"""
            ),
            {
                "repository_id": repository_id,
                "embedding": vector_literal(embedding),
                "limit": limit,
            },
        )
    ).mappings()
    return [dict(row) for row in rows]


async def semantic_search_repositories(
    session: AsyncSession,
    repository_ids: list[uuid.UUID],
    query: str,
    limit: int = 24,
) -> list[dict[str, Any]]:
    """Search one embedding across a Team repository pool for Intake scoping."""
    if not repository_ids:
        return []
    client = await embedding_client(session)
    embedding = (await client.embed([query]))[0]
    rows = (
        await session.execute(
            text(
                """SELECT repository_id, file_path, chunk_index, content, commit_sha,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
                   FROM knowledge_chunks
                   WHERE repository_id = ANY(CAST(:repository_ids AS uuid[]))
                   ORDER BY embedding <=> CAST(:embedding AS vector)
                   LIMIT :limit"""
            ),
            {
                "repository_ids": [str(repository_id) for repository_id in repository_ids],
                "embedding": vector_literal(embedding),
                "limit": limit,
            },
        )
    ).mappings()
    return [dict(row) for row in rows]
