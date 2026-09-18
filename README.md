# Autonomous Engineering Worker

A self-hosted system that takes authorized engineering tasks through code changes, validation, pull requests and guarded merges.

Built with Python/FastAPI, PostgreSQL and SvelteKit, with isolated Docker runners and an optional desktop launcher.

## Run locally

Configure Docker and `.env` using the [setup guide](docs/guide.md#local-setup), then:

```sh
sh scripts/start-local.sh --mode console
```

Open `http://localhost:3000`. Execution modes require configured credentials, repositories and budgets and can resume authorized queued work.

## Development

After installing the [prerequisites](docs/guide.md#code-quality):

```sh
make setup      # Install dependencies and the pre-push hook
make format     # Format project files
make pre-push   # Check formatting, lint and types
make check      # Also run tests and builds
```

Run `make dev-backend` and `make dev-frontend` in separate terminals. Existing checkouts can enable automatic push checks with `make hooks`.

## Documentation

- [Setup and development](docs/guide.md): configuration, code quality, hooks, desktop and deployment.
- [Architecture and workflow](docs/architecture.md): product behavior, modules, data and task-to-merge flow.
- [Evaluation and results](docs/evaluation.md): benchmark procedures, acceptance limits and recorded outcomes.
