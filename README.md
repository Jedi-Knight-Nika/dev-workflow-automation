# Autonomous Engineering Worker

<p align="center">
  <img src="docs/logo.png" alt="Autonomous Engineering Worker logo" width="220" />
</p>

> Automate the nine-to-five job hell. As one wise man said, if they don't give you a salary raise, promote yourself by working less.

An AI engineering workflow orchestrator that turns external or manually created tasks into
planned, implemented, tested, reviewed, and delivered code while deterministic software retains
control of routing, permissions, budgets, retries, and state.

The project is designed around durable jobs, isolated workers, auditable events, and
human control. AI models assist with reasoning and implementation; the application
controls scheduling, permissions, retries, and lifecycle decisions.

## Development

The application is containerized and can be started with:

```bash
cp .env.example .env
docker compose up --build
```

Read [PRODUCT.md](PRODUCT.md) for the complete product and architecture reference, and
[DEVELOPMENT.md](DEVELOPMENT.md) for setup, operations, and validation commands.

See [How AI task execution currently works](docs/ai-task-lifecycle-current.md) for an
English, source-backed walkthrough from task creation to merge, including role handoffs,
workspace tools, context, token budgets, and known completion limitations.

See [Project architecture and detailed feature inventory](docs/project-architecture-and-features.md)
for the technology stack, deployment, domain/data model, UI and API features,
integrations, security boundaries, operations, and current limitations.

See [Role-by-role efficiency research](docs/role-efficiency-research.md) for the latest
Planner, Executor, routing, review, and validation optimizations and their test evidence.

See [Token efficiency and execution budgets](docs/token-efficiency.md) for cost controls,
source-reading limits, plan reuse, and verification details.

See [Executor workspace tools](docs/executor-workspace-tools.md) for direct editing,
same-run test correction, permissions, and rollout instructions.

See [Token-cost research and recovery](docs/token-cost-research-and-recovery.md) for
the research-backed source-access, caching, and reimport/worktree fixes.
