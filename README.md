# Autonomous Engineering Worker

> Automate the nine-to-five job hell. As one wise man said, if they don't give you a salary raise, promote yourself by working less.

An engineering workflow automation system that coordinates planning, code execution,
review, and repository workflows while keeping authority and state in deterministic
software.

The project is designed around durable jobs, isolated workers, auditable events, and
human control. AI models assist with reasoning and implementation; the application
controls scheduling, permissions, retries, and lifecycle decisions.

## Development

The application is containerized and can be started with:

```bash
cp .env.example .env
docker compose up --build
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for local tooling and validation commands.
Implementation status is tracked in
[IMPLEMENTATION_PROGRESS.md](IMPLEMENTATION_PROGRESS.md).
