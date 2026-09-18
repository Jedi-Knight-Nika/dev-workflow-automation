"""A host-inode lock shared by Developer and validator containers for one task."""

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def workspace_lock(path: Path = Path("/run/workspace.lock")) -> Iterator[None]:
    # The bind is read-only, so task code cannot replace/unlink the locked inode.
    # A surviving container retains this lock even after its controller crashes.
    with path.open("rb") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another runner still owns this task workspace") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
