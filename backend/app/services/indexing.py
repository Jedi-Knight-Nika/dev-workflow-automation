import ast
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IndexStatus, Integration, Repository
from app.providers.embeddings import OpenAIEmbeddings
from app.services.crypto import cipher
from app.services.workspaces import prepare_repository_cache, run_git

MAX_FILE_BYTES = 200_000
CHUNK_CHARS = 4_000
CHUNK_OVERLAP = 400
IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".next",
        ".nuxt",
        ".pytest_cache",
        ".ruff_cache",
        ".svelte-kit",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "vendor",
        "venv",
    }
)
IGNORED_FILE_SUFFIXES = frozenset(
    {
        ".7z",
        ".avi",
        ".class",
        ".dll",
        ".dylib",
        ".eot",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".mov",
        ".mp3",
        ".mp4",
        ".o",
        ".pdf",
        ".png",
        ".pyc",
        ".so",
        ".tar",
        ".ttf",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".zip",
    }
)
SECRET_FILE_NAMES = frozenset({".env", ".npmrc", ".pypirc"})


@dataclass(frozen=True)
class SourceChunk:
    file_path: str
    index: int
    content: str
    content_hash: str
    symbol: str | None = None


def should_index_path(file_path: str) -> bool:
    path = PurePosixPath(file_path)
    lowered_parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    if not path.parts or path.is_absolute() or ".." in path.parts:
        return False
    if any(part in IGNORED_DIRECTORY_NAMES for part in lowered_parts[:-1]):
        return False
    if name in SECRET_FILE_NAMES or name.startswith(".env."):
        return False
    if path.suffix.lower() in IGNORED_FILE_SUFFIXES:
        return False
    return not name.endswith((".min.js", ".min.css", ".bundle.js", ".bundle.css"))


LANGUAGES = {
    ".css": "css",
    ".go": "go",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".mdx": "markdown",
    ".py": "python",
    ".rs": "rust",
    ".svelte": "svelte",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".yaml": "yaml",
    ".yml": "yaml",
}


def chunk_metadata(chunk: SourceChunk, indexed_at: datetime) -> dict[str, str | None]:
    suffix = PurePosixPath(chunk.file_path).suffix.lower()
    if chunk.symbol == "module":
        chunk_type = "module"
    elif chunk.symbol and suffix in {".md", ".mdx"}:
        chunk_type = "section"
    elif chunk.symbol:
        chunk_type = "symbol"
    else:
        chunk_type = "text"
    return {
        "language": LANGUAGES.get(suffix, suffix.removeprefix(".") or "text"),
        "symbol": chunk.symbol,
        "chunk_type": chunk_type,
        "last_indexed_at": indexed_at.isoformat(),
        "authority_level": "DERIVED_CODE",
    }


def chunks_requiring_embeddings(
    chunks: list[SourceChunk], cached_embeddings: dict[tuple[str, str], str]
) -> list[SourceChunk]:
    return [
        chunk for chunk in chunks if (chunk.file_path, chunk.content_hash) not in cached_embeddings
    ]


def chunk_text(file_path: str, content: str) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    start = 0
    index = 0
    while start < len(content):
        end = min(len(content), start + CHUNK_CHARS)
        if end < len(content):
            newline = content.rfind("\n", start + CHUNK_CHARS // 2, end)
            if newline > start:
                end = newline + 1
        value = content[start:end]
        chunks.append(
            SourceChunk(
                file_path=file_path,
                index=index,
                content=value,
                content_hash=hashlib.sha256(value.encode()).hexdigest(),
            )
        )
        if end >= len(content):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
        index += 1
    return chunks


SCRIPT_DECLARATION = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|interface|type|enum|const|let)\s+([A-Za-z_$][\w$]*)"
)
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


def _python_boundaries(content: str) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    return [
        (
            min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)]) - 1,
            node.name,
        )
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _script_boundaries(lines: list[str], svelte: bool) -> list[tuple[int, str]]:
    boundaries: list[tuple[int, str]] = []
    depth = 0
    inside_script = not svelte
    for index, line in enumerate(lines):
        stripped = line.strip()
        if svelte and stripped.startswith("<script"):
            inside_script = True
            continue
        if svelte and stripped.startswith("</script"):
            inside_script = False
            continue
        if not inside_script:
            continue
        candidate = stripped if svelte else line
        match = SCRIPT_DECLARATION.match(candidate) if depth == 0 else None
        if match:
            boundaries.append((index, match.group(1)))
        # This intentionally approximates syntax nesting without requiring a parser runtime.
        depth = max(0, depth + line.count("{") - line.count("}"))
    return boundaries


def _line_boundaries(file_path: str, lines: list[str]) -> list[tuple[int, str]]:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".svelte"}:
        return _script_boundaries(lines, suffix == ".svelte")
    boundaries: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = None
        if suffix in {".md", ".mdx"}:
            match = MARKDOWN_HEADING.match(line)
        if match:
            boundaries.append((index, match.group(1)))
    return boundaries


def chunk_source(file_path: str, content: str) -> list[SourceChunk]:
    lines = content.splitlines(keepends=True)
    suffix = Path(file_path).suffix.lower()
    boundaries = (
        _python_boundaries(content) if suffix == ".py" else _line_boundaries(file_path, lines)
    )
    if not boundaries:
        return chunk_text(file_path, content)
    if boundaries[0][0] > 0:
        boundaries.insert(0, (0, "module"))
    chunks: list[SourceChunk] = []
    for position, (start, symbol) in enumerate(boundaries):
        end = boundaries[position + 1][0] if position + 1 < len(boundaries) else len(lines)
        section = "".join(lines[start:end])
        for chunk in chunk_text(file_path, section):
            chunks.append(
                SourceChunk(
                    file_path=file_path,
                    index=len(chunks),
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    symbol=symbol,
                )
            )
    return chunks


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
        if len(raw.encode()) > MAX_FILE_BYTES or "\x00" in raw:
            continue
        chunks.extend(chunk_source(file_path, raw))
    return chunks


def parse_changed_paths(output: str) -> list[str]:
    return sorted({path.strip() for path in output.splitlines() if path.strip()})


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


def vector_literal(values: list[float]) -> str:
    if len(values) != 1536:
        raise ValueError(f"Expected 1536 embedding dimensions, received {len(values)}")
    return "[" + ",".join(str(value) for value in values) + "]"


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
