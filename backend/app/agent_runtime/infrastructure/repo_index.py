"""Bounded syntax intelligence, cached by SHA plus current source hashes.

References/callers are candidates, not type-resolved LSP results. No source execution.
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser

SYNTAX_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".svelte"}
EXTENSIONS = SYNTAX_EXTENSIONS | {
    ".html",
    ".css",
    ".scss",
    ".md",
    ".rst",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".rs",
    ".sh",
    ".sql",
}
EXCLUDED = {"node_modules", "dist", "build", "target", "vendor", "__pycache__"}
DEFINITIONS = {
    "function_definition",
    "class_definition",
    "function_declaration",
    "class_declaration",
    "method_definition",
    "interface_declaration",
    "type_alias_declaration",
    "variable_declarator",
}


@lru_cache(maxsize=6)
def parser_for(suffix: str) -> Parser:
    import tree_sitter_javascript as javascript
    import tree_sitter_python as python
    import tree_sitter_typescript as typescript

    language = (
        python.language()
        if suffix == ".py"
        else javascript.language()
        if suffix in {".js", ".jsx"}
        else typescript.language_tsx()
        if suffix == ".tsx"
        else typescript.language_typescript()
    )
    return Parser(Language(language))


def words(text: str) -> set[str]:
    split = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return {w for w in re.findall(r"[\w]+", split.casefold()) if len(w) >= 3}


def extract(path: str, raw: bytes) -> dict[str, Any]:
    suffix = Path(path).suffix
    text = raw.decode(errors="replace")
    chunks = [(raw, 0)] if suffix in SYNTAX_EXTENSIONS else []
    if suffix == ".svelte":
        chunks = [
            (m.group(1), raw[: m.start(1)].count(b"\n"))
            for m in re.finditer(rb"<script\b[^>]*>(.*?)</script>", raw, re.DOTALL)
        ]
    symbols: list[dict[str, Any]] = []
    references: set[str] = set()
    calls: set[str] = set()
    imports: set[str] = set()
    for chunk, offset in chunks:
        stack = [parser_for(suffix).parse(chunk).root_node]
        while stack:
            node = stack.pop()
            if node.type in DEFINITIONS:
                name = node.child_by_field_name("name")
                if name is not None and len(symbols) < 100:
                    symbols.append(
                        {
                            "name": chunk[name.start_byte : name.end_byte].decode(errors="replace")[
                                :100
                            ],
                            "kind": node.type,
                            "line": node.start_point.row + offset + 1,
                            "end": node.end_point.row + offset + 1,
                        }
                    )
            if node.type in {"identifier", "type_identifier"} and len(references) < 600:
                references.add(
                    chunk[node.start_byte : node.end_byte].decode(errors="replace")[:100]
                )
            if node.type in {"call", "call_expression"}:
                function = node.child_by_field_name("function")
                if function is not None and len(calls) < 200:
                    calls.add(
                        chunk[function.start_byte : function.end_byte].decode(errors="replace")[
                            :120
                        ]
                    )
            if node.type in {"import_statement", "import_from_statement"}:
                imports.add(chunk[node.start_byte : node.end_byte].decode(errors="replace")[:300])
            stack.extend(reversed(node.named_children))
    if suffix == ".svelte":
        symbols.insert(
            0,
            {"name": Path(path).stem, "kind": "component", "line": 1, "end": text.count("\n") + 1},
        )
        references.update(re.findall(r"<([A-Z][\w.]*)", text))
    return {
        "path": path,
        "symbols": symbols,
        "imports": sorted(imports)[:40],
        "references": sorted(references),
        "calls": sorted(calls),
        "search_words": sorted(words(text))[:2000],
        "test": "tests" in Path(path).parts or bool(re.search(r"[._](test|spec)[._]", path)),
        "routes": re.findall(r"@\w+\.(?:get|post|put|patch|delete)\([^\n]+", text)[:15],
        "entities": re.findall(r"__tablename__\s*=\s*['\"]([^'\"]+)", text)[:15],
    }


def _index_snapshot(workspace: Path, cache: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return syntax metadata and the bounded source snapshot used to fingerprint it."""
    root = workspace.resolve()
    try:
        sha = (
            subprocess.check_output(
                ["git", "-c", "safe.directory=" + str(root), "rev-parse", "HEAD"],
                cwd=root,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            .decode()
            .strip()
        )
    except (subprocess.SubprocessError, OSError):
        sha = "uncommitted"
    files: list[tuple[str, bytes]] = []
    total = 0
    partial = False
    digest = hashlib.sha256(("syntax-index-v2\0" + sha).encode())
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and d not in EXCLUDED
            and not (Path(directory) / d).is_symlink()
        )
        for name in sorted(names):
            path = Path(directory) / name
            if (
                (path.suffix not in EXTENSIONS and name not in {"Dockerfile", "Makefile"})
                or name.startswith(".")
                or path.is_symlink()
                or path.stat().st_size > 300000
            ):
                continue
            if len(files) >= 2500 or total >= 30_000_000:
                partial = True
                break
            raw = path.read_bytes()
            total += len(raw)
            relative = str(path.relative_to(root))
            digest.update(relative.encode() + b"\0" + hashlib.sha256(raw).digest())
            files.append((relative, raw))
        if partial:
            break
    key = digest.hexdigest()
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    saved = cache / "index.json"
    try:
        if saved.stat().st_size < 30_000_000:
            previous = json.loads(saved.read_text())
            if isinstance(previous, dict) and previous.get("key") == key:
                return previous, dict(files)
    except (OSError, ValueError):
        pass
    result = {
        "sha": sha,
        "key": key,
        "partial": partial,
        "files": [extract(path, raw) for path, raw in files],
    }
    with tempfile.NamedTemporaryFile(mode="w", dir=cache, delete=False) as output:
        json.dump(result, output)
        temporary = output.name
    os.replace(temporary, saved)
    return result, dict(files)


def investigate(
    workspace: Path,
    objective: str,
    cache: Path | None = None,
    *,
    include_source_slices: bool = True,
) -> dict[str, Any]:
    data, sources = _index_snapshot(workspace, cache or Path.home() / ".aew/tool-logs/repo-index")
    query = words(objective) - {"the", "and", "with", "from", "read", "only"}
    ranked = []
    tokens = re.findall(r"\w+", objective.casefold())
    phrases = {" ".join(tokens[i : i + 5]) for i in range(max(0, len(tokens) - 4))}
    for row in data["files"]:
        symbol_words = words(" ".join(s["name"] for s in row["symbols"]))
        matches = query & set(row["search_words"])
        score = 6 * len(query & words(row["path"])) + 4 * len(query & symbol_words) + len(matches)
        # Quoted UI copy is stronger localization evidence than generic words
        # such as worker, task, or build in unrelated backend symbols.
        if phrases:
            content = " ".join(
                re.findall(r"\w+", sources[row["path"]].decode(errors="replace").casefold())
            )
            score += 80 * min(8, sum(phrase in content for phrase in phrases))
        if row["test"]:
            score = score * 3 // 5
        if score:
            ranked.append((score, row, matches))
    ranked.sort(key=lambda item: (-item[0], item[1]["path"]))
    if ranked:
        # Once a clear target area exists, avoid flooding a UI task with similarly
        # named backend schemas. Still retain cross-area results if no local match.
        area = Path(ranked[0][1]["path"]).parts[0]
        ranked.sort(
            key=lambda item: (
                -(item[0] if Path(item[1]["path"]).parts[0] == area else item[0] // 3),
                item[1]["path"],
            )
        )
    # Reuse lookup values across the five candidate relationship scans.
    relationships = (
        [
            (
                row,
                Path(row["path"]).suffix == ".py",
                set(row["references"]),
                " ".join(row["imports"]),
                set(row["search_words"]),
            )
            for row in data["files"]
        ]
        if ranked
        else []
    )
    selected = []
    for score, row, matches in ranked[:5]:
        names = {
            s["name"]
            for s in row["symbols"]
            if (
                s["kind"] == "component"
                if row["path"].endswith(".svelte")
                else s["kind"] != "variable_declarator" and len(s["name"]) >= 8
            )
        }
        target = Path(row["path"])
        target_words = words(target.stem) - {"modal", "component", "test"}
        related = [
            r
            for r, is_python, references, imports, search_words in relationships
            if r["path"] != row["path"]
            and is_python == (target.suffix == ".py")
            and (
                names & references
                or target.stem in imports
                or r["test"]
                and len(target_words) >= 2
                and target_words <= search_words
            )
        ]
        selected.append(
            {
                "path": row["path"],
                "matched": sorted(matches)[:8],
                "symbols": sorted(row["symbols"], key=lambda s: s["kind"] == "variable_declarator")[
                    :8
                ],
                "imports": row["imports"][:4],
                "candidate_callers": [r["path"] for r in related if not r["test"]][:3],
                "related_tests": [r["path"] for r in related if r["test"]][:3],
                "routes": row["routes"][:3],
                "entities": row["entities"][:3],
            }
        )
    while len(json.dumps(selected, ensure_ascii=False).encode()) > 6500 and selected:
        selected.pop()
    slices = []
    for row in selected[:3] if include_source_slices else []:
        path = workspace / row["path"]
        if path.is_symlink() or not path.resolve().is_relative_to(workspace.resolve()):
            continue
        lines = sources[row["path"]].decode(errors="replace").splitlines()
        hit = next(
            (
                i
                for i, line in enumerate(lines)
                if len(query & words(line)) >= 2 and not line.strip().startswith("import ")
            ),
            0,
        )
        start = max(0, hit - 8)
        snippet = "\n".join(lines[start : start + 65])
        slices.append(
            {
                "path": row["path"],
                "start_line": start + 1,
                "text": snippet[:1800],
                "truncated": start > 0 or len(lines) > 65 or len(snippet) > 1800,
            }
        )
    return {
        "sha": data["sha"],
        "partial_index": data["partial"],
        "repo_map": selected,
        "candidate_paths": [row["path"] for row in selected],
        "source_slices": slices,
        "note": "Tree-sitter syntax evidence; callers/tests are name-reference candidates, not LSP resolution. Original requirement remains authoritative. Edit when sufficient; inspect a narrower range only if needed.",
    }
