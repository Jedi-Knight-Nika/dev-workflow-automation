import ntpath
from pathlib import Path, PureWindowsPath


class WorkspaceEscapeError(PermissionError):
    pass


def resolve_workspace_path(
    workspace: Path, requested: str | Path, *, must_exist: bool = False
) -> Path:
    root = workspace.resolve(strict=True)
    raw = Path(requested)
    candidate = raw if raw.is_absolute() else root / raw
    try:
        resolved = candidate.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceEscapeError("Workspace target cannot be resolved safely") from exc
    if not resolved.is_relative_to(root):
        raise WorkspaceEscapeError("Target is outside the assigned task workspace")
    return resolved


def windows_path_is_within(workspace: str, requested: str) -> bool:
    """Lexical Windows ancestry guard; native runtime must additionally resolve junctions."""
    root = ntpath.normcase(ntpath.abspath(workspace))
    target = ntpath.normcase(ntpath.abspath(ntpath.join(root, requested)))
    try:
        return (
            ntpath.commonpath((root, target)) == root
            and PureWindowsPath(root).drive == PureWindowsPath(target).drive
        )
    except ValueError:
        return False
