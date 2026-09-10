"""Shared checkout boundary for runner tools, independent of the coding harness."""

from pathlib import Path


def source_path(workspace: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or any(
        part.startswith(".") or part in {"node_modules", "vendor"} for part in relative.parts
    ):
        raise ValueError("Use a checkout-relative source path, not metadata or dependencies")
    path = workspace / relative
    if any(
        parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(workspace)
    ):
        raise ValueError("Symlinked source paths are not supported")
    if not path.resolve().is_relative_to(workspace.resolve()) or path.is_symlink():
        raise ValueError("Source path escapes the checkout")
    return path
