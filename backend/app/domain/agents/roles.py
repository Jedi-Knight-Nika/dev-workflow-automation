from app.domain.operational_states import JobRole

# A role is one domain concept whether it is viewed from an Agent or a Job.
# Keep the AgentRole name as a compatibility alias for API and UI-facing code.
AgentRole = JobRole
