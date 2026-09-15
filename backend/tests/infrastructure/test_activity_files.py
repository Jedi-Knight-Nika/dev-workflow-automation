import subprocess

import pytest

from app.activity.infrastructure.files import committed_changes, parse_changes


def test_git_metadata_handles_rename_spaces_and_binary_sizes():
    files = parse_changes(
        b"R100\0old name.txt\0new name.txt\0M\0image.png\0",
        b"0\t0\t\0old name.txt\0new name.txt\0-\t-\timage.png\0",
    )
    assert files == [
        {
            "operation": "R",
            "path": "new name.txt",
            "previous_path": "old name.txt",
            "lines_added": 0,
            "lines_deleted": 0,
        },
        {
            "operation": "M",
            "path": "image.png",
            "previous_path": None,
            "lines_added": None,
            "lines_deleted": None,
        },
    ]


async def test_collector_reads_only_the_requested_commit_and_rejects_workspace_escape(tmp_path):
    workspace = tmp_path / "repository"
    workspace.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(workspace), *args]).decode().strip()

    git("init", "-q")
    git("config", "user.name", "Activity test")
    git("config", "user.email", "activity@example.test")
    (workspace / "example.txt").write_text("committed\n")
    git("add", "example.txt")
    git("-c", "commit.gpgsign=false", "commit", "-qm", "Initial")
    revision = git("rev-parse", "HEAD")
    (workspace / "example.txt").write_text("uncommitted secret\n")
    (workspace / "private.txt").write_text("private\n")
    before = git("status", "--porcelain")
    files = await committed_changes(workspace, tmp_path, revision)
    assert files == [
        {
            "operation": "A",
            "path": "example.txt",
            "previous_path": None,
            "lines_added": 1,
            "lines_deleted": 0,
        }
    ]
    assert git("status", "--porcelain") == before
    (tmp_path / "unrelated").mkdir()
    with pytest.raises(ValueError, match="outside"):
        await committed_changes(workspace, tmp_path / "unrelated", revision)
    with pytest.raises(ValueError, match="identity"):
        await committed_changes(workspace, tmp_path, "--all")


def test_oversized_commit_is_explicitly_terminal():
    from app.activity.infrastructure.files import FileHistoryError

    status = b"".join(f"A\0file-{index}.py\0".encode() for index in range(201))
    with pytest.raises(FileHistoryError) as error:
        parse_changes(status, b"")
    assert error.value.status == "TOO_LARGE"
