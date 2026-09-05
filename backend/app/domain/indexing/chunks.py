from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceChunk:
    file_path: str
    index: int
    content: str
    content_hash: str
    symbol: str | None = None


def chunks_requiring_embeddings(
    chunks: list[SourceChunk], cached_embeddings: dict[tuple[str, str], str]
) -> list[SourceChunk]:
    return [
        chunk for chunk in chunks if (chunk.file_path, chunk.content_hash) not in cached_embeddings
    ]
