# Autonomous Engineering Worker

> Automate the nine-to-five job hell. As one wise man said, if they don't give you a salary raise, promote yourself by working less.

An AI engineering workflow orchestrator that turns external or manually created tasks into
planned, implemented, tested, reviewed, and delivered code while deterministic software retains
control of routing, permissions, budgets, retries, and state.

The project is designed around durable jobs, isolated workers, auditable events, and
human control. AI models assist with reasoning and implementation; the application
controls scheduling, permissions, retries, and lifecycle decisions.

## V2 implementation

The [V2 technical specification](autonomous_engineering_worker_v2_technical_architecture.md)
is the target architecture and takes precedence over legacy workflow descriptions.
Read [implementation status and rollout](docs/v2-implementation.md) before enabling
anything: fixed-phase scheduling, native-runner transport, isolated validation and
PR/review/merge orchestration are implemented. Real Docker/native-provider acceptance
and the live-ticket benchmark are still outstanding.

The obsolete graph/Role editors and web terminals have been removed. Teams now
open the fixed lifecycle/profile page; old bookmarks redirect there. The scheduler
only dispatches V2 phases; it no longer runs the legacy model/patch or indexing loops.

Use the [fresh initial setup guide](docs/initial-setup.md). The old 59-revision MVP
upgrade chain has been replaced with one frozen initial schema and safe default
entities. Existing databases are refused, never automatically wiped or stamped.
Repository RAG is unsupported by this baseline; coding reads the current checkout.
Explicit [native session changes](docs/v2-implementation.md#explicit-session-changes)
preserve task usage and require a separate resume.

## Local development

With a new empty PostgreSQL volume, start the API/UI without paid execution:

```bash
cp .env.example .env
docker compose up --build
```

Read [PRODUCT.md](PRODUCT.md) for the complete product and architecture reference, and
[DEVELOPMENT.md](DEVELOPMENT.md) for setup, operations, and validation commands.
