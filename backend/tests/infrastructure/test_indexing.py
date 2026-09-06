from datetime import UTC, datetime

import pytest

from app.domain.indexing import (
    CHUNK_OVERLAP,
    SourceChunk,
    chunk_metadata,
    chunk_source,
    chunk_text,
    chunks_requiring_embeddings,
    parse_changed_paths,
    should_index_path,
    vector_literal,
)


def test_chunking_is_deterministic_and_overlapping() -> None:
    content = "a" * 4500
    chunks = chunk_text("src/example.py", content)

    assert len(chunks) == 2
    assert chunks[0].index == 0
    assert chunks[1].index == 1
    assert chunks[0].content[-CHUNK_OVERLAP:] == chunks[1].content[:CHUNK_OVERLAP]
    assert chunks[0].content_hash == chunk_text("src/example.py", content)[0].content_hash


def test_vector_literal_enforces_database_dimensions() -> None:
    value = vector_literal([0.0] * 1536)
    assert value.startswith("[0.0,0.0")

    with pytest.raises(ValueError, match="1536"):
        vector_literal([0.0])


def test_changed_paths_are_deduplicated_and_sorted() -> None:
    assert parse_changed_paths("src/z.py\nsrc/a.py\nsrc/z.py\n\n") == ["src/a.py", "src/z.py"]


@pytest.mark.parametrize(
    "path",
    [
        "node_modules/package/index.js",
        "frontend/.svelte-kit/output.js",
        "backend/.venv/lib/module.py",
        "dist/application.js",
        "coverage/report.json",
        "assets/logo.png",
        "static/application.min.js",
        ".env",
        ".env.production",
        ".npmrc",
        "../outside.py",
    ],
)
def test_repository_index_rejects_generated_binary_and_secret_paths(path: str) -> None:
    assert not should_index_path(path)


@pytest.mark.parametrize(
    "path", ["src/application.py", "frontend/src/app.svelte", "docs/setup.md", "package.json"]
)
def test_repository_index_accepts_source_and_project_metadata(path: str) -> None:
    assert should_index_path(path)


def test_python_source_is_chunked_at_top_level_symbols() -> None:
    content = (
        '"""Module docs."""\n\nVALUE = 1\n\ndef alpha():\n    return 1\n\nclass Beta:\n    pass\n'
    )
    chunks = chunk_source("src/example.py", content)

    assert [chunk.symbol for chunk in chunks] == ["module", "alpha", "Beta"]
    assert "Module docs" in chunks[0].content
    assert chunks[1].content.startswith("def alpha")
    assert "".join(chunk.content for chunk in chunks) == content


def test_typescript_and_markdown_use_declaration_boundaries() -> None:
    typescript = "import x from 'x';\n\nexport function run() {}\n\nexport class Worker {}\n"
    markdown = "Intro\n\n# Setup\nText\n\n## Run\nMore\n"

    assert [chunk.symbol for chunk in chunk_source("worker.ts", typescript)] == [
        "module",
        "run",
        "Worker",
    ]
    assert [chunk.symbol for chunk in chunk_source("README.md", markdown)] == [
        "module",
        "Setup",
        "Run",
    ]


def test_chunk_metadata_contains_design_contract_fields() -> None:
    indexed_at = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    chunk = SourceChunk("docs/setup.md", 0, "# Setup", "hash", "Setup")

    assert chunk_metadata(chunk, indexed_at) == {
        "language": "markdown",
        "symbol": "Setup",
        "chunk_type": "section",
        "last_indexed_at": "2026-09-05T12:00:00+00:00",
        "authority_level": "DERIVED_CODE",
    }


def test_incremental_index_only_embeds_chunks_with_new_content_hashes() -> None:
    unchanged = SourceChunk("src/app.py", 0, "old", "same-hash", "module")
    changed = SourceChunk("src/app.py", 1, "new", "new-hash", "run")

    assert chunks_requiring_embeddings(
        [unchanged, changed], {("src/app.py", "same-hash"): "[0.1,0.2]"}
    ) == [changed]
