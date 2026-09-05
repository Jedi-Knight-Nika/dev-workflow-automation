import hashlib
from datetime import datetime
from pathlib import PurePosixPath

from app.domain.indexing.chunks import SourceChunk

CHUNK_CHARS = 4_000
CHUNK_OVERLAP = 400

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
