import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    CREATE = "CREATE"
    REQUIREMENT_CHANGE = "REQUIREMENT_CHANGE"
    FEEDBACK = "FEEDBACK"
    APPROVAL = "APPROVAL"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"
    IGNORE = "IGNORE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Event:
    provider: str
    external_id: str
    kind: str
    actor: str
    body: str = ""
    task_reference: str | None = None
    head_sha: str | None = None
    authenticated: bool = False


@dataclass(frozen=True)
class Interpretation:
    intent: Intent
    confidence: float
    reason: str
    requires_authorization: bool = False


def requirement_fingerprint(title: str, description: str) -> str:
    """Provider status/priority/heartbeat changes are not new requirements."""
    content = json.dumps(
        {"title": title.strip(), "description": description.strip()},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(content.encode()).hexdigest()


def classify(event: Event) -> Interpretation | None:
    """Return None only for free text worth sending to a small interpreter.

    Callers verify signatures and construct kind/actor from the provider envelope,
    never from fields suggested by a model or free-text message.
    """
    if not event.authenticated:
        return Interpretation(Intent.IGNORE, 1, "Unverified event")
    if event.kind in {
        "task_created",
        "task_updated",
        "review_changes_requested",
        "review_approved",
        "checks_updated",
        "pull_request_merged",
    }:
        intent = {
            "task_created": Intent.CREATE,
            "task_updated": Intent.REQUIREMENT_CHANGE,
            "review_changes_requested": Intent.FEEDBACK,
            "review_approved": Intent.APPROVAL,
            "checks_updated": Intent.IGNORE,
            "pull_request_merged": Intent.IGNORE,
        }[event.kind]
        return Interpretation(intent, 1, "Structured provider event", intent == Intent.APPROVAL)
    if event.kind != "comment":
        return Interpretation(Intent.IGNORE, 1, "Unsupported event kind")
    command = re.fullmatch(r"/(pause|resume|cancel)\s+([A-Za-z0-9_-]+)", event.body.strip())
    if command and event.task_reference == command[2]:
        return Interpretation(Intent(command[1].upper()), 1, "Explicit command", True)
    feedback = re.fullmatch(r"/feedback\s+([A-Za-z0-9_-]+)\s+(.+)", event.body.strip(), re.DOTALL)
    if feedback and event.task_reference == feedback[1]:
        return Interpretation(Intent.FEEDBACK, 1, "Explicit feedback command", True)
    # An approval intent still requires authenticated human/current-SHA policy
    # checks. Exact common phrases avoid an unnecessary model call; prose with
    # conditions, negations or questions must go through bounded interpretation.
    approval = event.body.strip().casefold().rstrip(".!").strip()
    if (
        event.provider == "github"
        and event.head_sha
        and approval
        in {
            "lgtm",
            "looks good to me",
            "approved",
            "ready to merge",
            "merge it",
            "go ahead and merge",
            "please merge",
            "please merge it",
            "ship it",
        }
    ):
        return Interpretation(Intent.APPROVAL, 1, "Explicit human approval wording", True)
    return None
