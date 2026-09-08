# Autonomous Engineering Worker

A self-hosted engineering control plane that turns authorized work into validated pull requests through persistent native coding sessions, deterministic delivery, guarded merge, and live operational analytics.

See [PRODUCT_DESCRIPTION.md](PRODUCT_DESCRIPTION.md) for the complete product, architecture, setup, security, API, operations, and acceptance reference.

Start the configured local application:

```sh
docker compose up -d --build --wait
```

The UI is available at `http://localhost:3000` and the API at `http://localhost:8000/api`.
