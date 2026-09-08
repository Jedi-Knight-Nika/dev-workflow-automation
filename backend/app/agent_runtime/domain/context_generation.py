from dataclasses import dataclass


@dataclass(frozen=True)
class ContextCapabilities:
    supports_compaction: bool
    supports_active_context_measurement: bool
    supports_streaming_usage: bool
    supports_fresh_context_start: bool = True
    supports_resume: bool = True
    supports_tool_result_clearing: bool = False


CODEX_CAPABILITIES = ContextCapabilities(True, True, True)
CLAUDE_CAPABILITIES = ContextCapabilities(True, True, True)
