from dataclasses import dataclass

from app.delivery.domain.review import ReviewMessage


@dataclass(frozen=True)
class Approval:
    actor_id: str
    head_sha: str
    evidence_id: str
    formal: bool = True


@dataclass(frozen=True)
class MergeEvidence:
    expected_sha: str
    current_sha: str
    validated_sha: str | None
    pr_open: bool
    checks_complete: bool
    checks_passed: bool
    blocking_review: bool
    mergeable: bool | None
    task_runnable: bool
    approval: Approval | None
    review_messages: tuple[ReviewMessage, ...] = ()
    pending_review_messages: bool = False


@dataclass(frozen=True)
class MergePolicy:
    team_auto_merge: bool = False
    repository_auto_merge: bool = False
    authorized_actor_ids: frozenset[str] = frozenset()
    require_formal_approval: bool = True
    any_human_reviewer: bool = False

    def allows_actor(self, actor_id: str) -> bool:
        return bool(actor_id) and (self.any_human_reviewer or actor_id in self.authorized_actor_ids)

    def blockers(self, evidence: MergeEvidence) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.team_auto_merge or not self.repository_auto_merge:
            reasons.append("AUTO_MERGE_DISABLED")
        if not evidence.pr_open:
            reasons.append("PR_NOT_OPEN")
        if not evidence.expected_sha or evidence.current_sha != evidence.expected_sha:
            reasons.append("HEAD_CHANGED")
        if evidence.validated_sha != evidence.current_sha or not evidence.validated_sha:
            reasons.append("VALIDATION_STALE")
        if not evidence.checks_complete or not evidence.checks_passed:
            reasons.append("CHECKS_NOT_GREEN")
        if evidence.blocking_review:
            reasons.append("BLOCKING_REVIEW")
        if evidence.pending_review_messages:
            reasons.append("REVIEW_MESSAGES_PENDING")
        if evidence.mergeable is not True:
            reasons.append("MERGEABILITY_UNCONFIRMED")
        if not evidence.task_runnable:
            reasons.append("TASK_SUSPENDED")
        approval = evidence.approval
        if approval is None or not approval.evidence_id:
            reasons.append("APPROVAL_MISSING")
        else:
            if not self.allows_actor(approval.actor_id):
                reasons.append("APPROVER_UNAUTHORIZED")
            if approval.head_sha != evidence.current_sha:
                reasons.append("APPROVAL_STALE")
            if self.require_formal_approval and not approval.formal:
                reasons.append("FORMAL_APPROVAL_REQUIRED")
        return tuple(reasons)
