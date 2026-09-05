from pathlib import PurePosixPath

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
