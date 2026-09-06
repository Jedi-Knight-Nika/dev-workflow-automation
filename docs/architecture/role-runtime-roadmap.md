# Role runtime configuration roadmap

1. Persist normalized Role runtime defaults and an override policy.
2. Store only explicit runtime overrides on concrete Agents.
3. Validate provider/model settings through a conservative, versioned capability registry.
4. Resolve Role → Agent → Job strategy into one immutable effective runtime configuration.
5. Enforce the resolved timeout, model-turn, output, context, and tool-call limits.
6. Persist a sanitized configuration snapshot and hash with every WorkerRun.
7. Expose inheritance-aware Role editing and effective runtime previews.

The runtime profile never contains credentials or raw provider SDK keyword arguments.
Permissions remain independently resolved and Agent overrides remain reduction-only.
