import json
from dataclasses import dataclass
from typing import Any

from app.agent_runtime.domain.envelope import AgentEnvelope
from app.agent_runtime.domain.handoffs import work_packet
from app.agent_runtime.domain.session_changes import continuation_request, handoff_request
from app.agent_runtime.infrastructure.agent_codec import decode
from app.agent_runtime.infrastructure.models import DeveloperSession
from app.engineering.application.jobs import PhaseBlocked
from app.engineering.domain.lifecycle import WaitReason
from app.engineering.infrastructure.task_models import Task


@dataclass(frozen=True)
class DeveloperRequest:
    request: str
    feedback: str | None
    prompt: str
    rollover: dict[str, Any] | None
    work: AgentEnvelope | None


def build_developer_request(
    task: Task,
    native: DeveloperSession,
    requirement: str,
    *,
    supervisor_guidance: str = "",
    patch_resume_allowed: bool = False,
    compaction: bool = False,
    continuity: bool = False,
) -> DeveloperRequest:
    request = requirement
    checkpoint_digest = native.checkpoint.get("rollover_digest")
    if native.checkpoint.get("repair_packet") and not native.native_session_id:
        request += (
            "\nCURRENT REPAIR EVIDENCE (not a replacement requirement):\n"
            + json.dumps(native.checkpoint["repair_packet"], ensure_ascii=False)
            + "\nFix only the current delta. Do not reconstruct the previous conversation."
        )
    starting_generation = not native.native_session_id
    continuing_checkpoint = checkpoint_digest and native.checkpoint.get("continuation_pending")
    rollover = None
    if starting_generation or continuing_checkpoint:
        rollover = native.checkpoint.get("rollover_checkpoint")
    if rollover:
        if rollover.get("requirement_version") != task.requirement_version:
            raise PhaseBlocked(
                WaitReason.MISSING_REQUIREMENT, "Checkpoint requirement version changed"
            )
        try:
            request = continuation_request(request, rollover)
        except ValueError as exc:
            raise PhaseBlocked(WaitReason.MISSING_REQUIREMENT, str(exc)) from exc
    if not native.native_session_id and native.checkpoint.get("handoff"):
        handoff = native.checkpoint["handoff"]
        request = handoff_request(
            request,
            str(handoff.get("summary") or ""),
            str(handoff.get("note") or ""),
            str(native.checkpoint.get("next_feedback") or ""),
        )
    feedback = (
        str(native.checkpoint.get("next_feedback") or "").strip()
        if native.native_session_id
        else None
    )
    if continuity:
        request = (
            "Acknowledge the current objective and this verified checkpoint with exactly ACK "
            + str(checkpoint_digest)
            + "\n"
            + json.dumps(rollover, ensure_ascii=True)
        )
        feedback = None
    elif (rollover or patch_resume_allowed) and native.native_session_id:
        feedback = request
    if native.native_session_id and not feedback:
        raise PhaseBlocked(
            WaitReason.MISSING_REQUIREMENT,
            "A resumed session needs new feedback; do not replay the old task",
        )
    prompt = feedback if feedback is not None else request
    if supervisor_guidance:
        if feedback is not None:
            feedback += supervisor_guidance
        else:
            request += supervisor_guidance
        prompt = feedback if feedback is not None else request
    invariants: tuple[str, ...] = ()
    guidance = native.checkpoint.get("coordinator_guidance")
    if guidance and not compaction and not continuity:
        packet = decode(json.dumps(guidance), "JSON_VERBOSE")
        if (packet.task_id, packet.requirement_revision, packet.current_sha) != (
            task.id,
            task.requirement_version,
            task.current_revision,
        ):
            raise PhaseBlocked(WaitReason.MISSING_REQUIREMENT, "Coordinator handoff is stale")
        invariants = tuple(packet.payload.get("invariants", []))
        delta = str(packet.payload["request"])
        if delta not in prompt:
            prompt += "\nCurrent authorized change request:\n" + delta
        prompt += (
            "\nRequired invariants:\n" + json.dumps(list(invariants), ensure_ascii=False)
            if invariants
            else ""
        )
        if feedback is not None:
            feedback = prompt
        else:
            request = prompt
    work = (
        work_packet(
            task.id,
            task.requirement_version,
            task.current_revision,
            prompt,
            repair=task.stage == "FIXING",
            invariants=invariants,
        )
        if not compaction and not continuity
        else None
    )
    return DeveloperRequest(
        request=request, feedback=feedback, prompt=prompt, rollover=rollover, work=work
    )
