def agent_status(*, enabled: bool, model: str, active_jobs: int) -> str:
    if not enabled:
        return "DISABLED"
    if not model:
        return "NEEDS_CONFIGURATION"
    if active_jobs:
        return "RUNNING"
    return "READY"
