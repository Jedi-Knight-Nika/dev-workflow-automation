import ast
import re
from pathlib import Path

from app.domain.indexing.chunks import SourceChunk
from app.domain.indexing.text_chunks import chunk_text

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
        depth = max(0, depth + line.count("{") - line.count("}"))
    return boundaries


def _line_boundaries(file_path: str, lines: list[str]) -> list[tuple[int, str]]:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".svelte"}:
        return _script_boundaries(lines, suffix == ".svelte")
    boundaries: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = MARKDOWN_HEADING.match(line) if suffix in {".md", ".mdx"} else None
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
