# Autonomous Engineering Worker

> Automate the nine-to-five job hell. As one wise man said, if they don't give you a salary raise, promote yourself by working less.

An AI engineering workflow orchestrator that turns external or manually created tasks into
planned, implemented, tested, reviewed, and delivered code while deterministic software retains
control of routing, permissions, budgets, retries, and state.

The project is designed around durable jobs, isolated workers, auditable events, and
human control. AI models assist with reasoning and implementation; the application
controls scheduling, permissions, retries, and lifecycle decisions.

## V2 architecture migration

The [V2 technical specification](autonomous_engineering_worker_v2_technical_architecture.md)
is the target architecture and takes precedence over legacy workflow descriptions.
Read [implementation status and rollout](docs/v2-implementation.md) before enabling
anything: fixed-phase scheduling, native-runner transport and isolated validation are
implemented behind flags, but this is **not yet a
production replacement for the legacy worker**. Existing tasks/history are preserved.

The obsolete graph/Role editors and web terminals have been removed. Teams now
open the fixed lifecycle/profile page; old bookmarks redirect there. Task enrollment
and V2 publication/merge still need completion before switching production execution.

Repository RAG is off by default. Set `REPOSITORY_RAG_ENABLED=true` explicitly to
enable repository indexing and retrieval; normal coding uses current workspaces.

## Local development

The application is containerized and can be started with:

```bash
cp .env.example .env
docker compose up --build
```

Read [PRODUCT.md](PRODUCT.md) for the complete product and architecture reference, and
[DEVELOPMENT.md](DEVELOPMENT.md) for setup, operations, and validation commands.
