# Resilience implementation roadmap

The resilience layer extends the existing scheduler, Job state machine, provider adapters,
incident service, and task event log. It does not introduce a second orchestrator.

1. **Failure contract** — classify provider, model, worker, tool, integration, policy, and
   engineering failures into safe typed decisions.
2. **Durable retry state** — add waiting Job states, category-specific retry counters, and
   failure events without consuming engineering-loop budgets for infrastructure failures.
3. **Shared health and circuit state** — persist provider/integration health and enforce
   CLOSED, OPEN, and HALF_OPEN transitions across scheduler processes.
4. **Incident aggregation** — reuse stable Incident fingerprints and existing notification
   routing for action-required and critical failures.
5. **Recovery** — release workers while dependencies are unavailable and gradually requeue
   eligible Jobs after the circuit cooldown.
6. **Scheduler integration** — run recovery preflight before claiming more work and record
   provider recovery after a successful Job.
7. **Verification** — unit-test classification, retry decisions, circuit transitions, and
   recovery; run the existing PostgreSQL integration tier.

Deferred until production evidence warrants them: automatic resource-tier increases,
arbitrary cross-provider fallback, active provider probe traffic, a platform kill-switch UI,
and broad chaos infrastructure.
