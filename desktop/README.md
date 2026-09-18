# Desktop launcher

This Tauri wrapper displays the local web console. It delegates startup to the repository's `scripts/start-local.sh`, waits for the frontend on port 3000, and displays startup errors instead of navigating to an unavailable page.

## Prerequisites

- Install Docker with Compose, Rust/Tauri platform dependencies, and Node.js.
- Configure the repository `.env` and required mounts as described in `../PRODUCT_DESCRIPTION.md`.
- Build the desired stack once from the repository root, for example `sh scripts/start-local.sh --mode console`. The desktop launcher uses `--no-build`; rebuild images explicitly after source changes.

## Run

From this directory:

```sh
npm ci
npm run tauri dev
```

Debug builds locate the repository relative to `src-tauri`. Packaged builds require `AEW_REPO_ROOT` pointing to the checkout containing `compose.yaml` and `scripts/start-local.sh`.

The desktop default is `console`, preserving its non-executing base-Compose behavior. Set `AEW_START_MODE=execution` or `AEW_START_MODE=full` in the launch environment to opt into execution or execution plus monitoring. These modes can resume authorized queued work; they still require configured runtime credentials, repository access, and spending policy. The shell script alone defaults to `full` for compatibility with its existing callers.

The launcher starts services; closing the window does not stop them. It is a local wrapper, not an installer or a production deployment manager.
