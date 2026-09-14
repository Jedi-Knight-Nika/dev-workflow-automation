"""Small task-independent project facts, rebuilt from current checkout evidence.

Repository files are the durable memory: no model summaries, old ticket history,
absolute worktree paths or commit IDs enter this reusable prefix.
"""

import hashlib
import json
import tomllib
from pathlib import Path

from app.agent_runtime.infrastructure.source_paths import source_path

MAX_CONTEXT_BYTES = 6000
MANIFESTS = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod")


def repository_context(workspace: Path) -> dict[str, str]:
    roots = [""]
    # Bounded, deterministic layout sampling; never traverse dependencies or symlinks.
    roots.extend(
        p.name
        for p in sorted(workspace.iterdir())
        if p.is_dir()
        and not p.is_symlink()
        and not p.name.startswith(".")
        and p.name not in {"node_modules", "vendor", "dist", "build", "target", "__pycache__"}
    )
    roots = roots[:25]
    facts = [
        "Repository directories (bounded): "
        + ", ".join(roots[1:]).encode()[:1800].decode("utf-8", errors="ignore")
    ]
    remaining = MAX_CONTEXT_BYTES - len(facts[0].encode()) - 2
    for root in roots:
        names = ("AGENTS.md", "README.md", *MANIFESTS) if not root else MANIFESTS
        for filename in names:
            name = str(Path(root) / filename)
            try:
                path = source_path(workspace, name)
                if not path.is_file() or path.stat().st_size > 100000:
                    continue
                raw = path.read_text(encoding="utf-8")
                if filename == "package.json":
                    data = json.loads(raw)
                    data = {
                        k: data[k]
                        for k in ("name", "packageManager", "scripts", "workspaces")
                        if k in data
                    }
                    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
                elif filename in {"pyproject.toml", "Cargo.toml"}:
                    data = tomllib.loads(raw)
                    raw = json.dumps(
                        {
                            "name": data.get("project", data.get("package", {})).get("name"),
                            "tools": sorted(data.get("tool", {})),
                            "workspace": data.get("workspace", {}).get("members", []),
                            "build_system": data.get("build-system", {}),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                budget = min(
                    1800 if filename == "AGENTS.md" else 1000, remaining - len(name.encode()) - 40
                )
                if budget <= 0:
                    continue
                excerpt = raw.encode()[:budget].decode("utf-8", errors="ignore")
                if excerpt != raw:
                    excerpt += "\n[excerpt; omitted content unknown]"
                entry = name + ":\n" + excerpt
                facts.append(entry)
                remaining -= len(entry.encode()) + 2
            except (OSError, ValueError, TypeError, AttributeError):
                continue  # Optional context must not block otherwise valid source localization.
    text = "\n\n".join(facts)
    return {"fingerprint": hashlib.sha256(text.encode()).hexdigest(), "text": text}
