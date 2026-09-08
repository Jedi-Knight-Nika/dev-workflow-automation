from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequestDetails:
    number: int
    url: str
    state: str
    head_sha: str
    merged: bool = False
    merge_commit_sha: str | None = None


@dataclass(frozen=True)
class MergeReceipt:
    merged: bool
    message: str
    sha: str | None = None
