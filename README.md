# Autonomous Engineering Worker

A self-hosted engineering control plane that turns authorized work into validated pull requests through persistent native coding sessions, deterministic delivery, guarded merge, and live operational analytics.

See [PRODUCT_DESCRIPTION.md](PRODUCT_DESCRIPTION.md) for the complete product, architecture, setup, security, API, operations, and acceptance reference.

The [full architecture and workflow report](docs/project-architecture-and-workflow.md) explains the technology stack, module ownership, data model, runtime processes, task-to-commit/push/merge flow, frontend, security, operations, and extension guidelines.

The [Coordinator rollout guide](docs/coordinator-implementation.md) covers event-driven conversations, human clarification, execution queues, spending controls, configuration, and experimental model/protocol evaluation.

The [activity replay guide](docs/activity-visualizer.md) covers the optional read-only viewer, projection architecture, deployment settings, and historical data limits.

After configuring `.env` and the prerequisites in the product reference, start the local console:

```sh
sh scripts/start-local.sh --mode console
```

The UI is available at `http://localhost:3000` and the API at `http://localhost:8000/api`.

Use `--mode execution` to include native execution, or `--mode full` to also include monitoring and alerts. Execution requires configured runtimes, credentials, repository access, and spending policy; enabling it can resume authorized queued work. The script defaults to `full` when no mode or `AEW_START_MODE` is supplied, preserving its previous behavior. `--no-build` reuses images and does not deploy source changes.

For development, `make dev-backend` and `make dev-frontend` run separate servers; the frontend proxies `/api` to `http://localhost:8000` by default. `make test` runs backend and frontend unit suites; database integration tests require an isolated `TEST_DATABASE_URL`. Browser tests remain a separate `make frontend-e2e` command.

## Code quality

Use Node.js 22.13+ (or a supported newer LTS), Python 3.12+, uv, and Rust with the `rustfmt` and `clippy` components. The desktop check also needs the platform's Tauri build dependencies. On macOS, install shell tools with `brew install shellcheck shfmt`; other platforms can use the upstream binaries or their package manager. Run `make setup` to install the locked Python and frontend dependencies. Desktop JavaScript reuses the frontend tooling; there is no second linter dependency tree.

| Files                                                                  | Tools                                                                                                          |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Python application, migrations, tests, evaluations and utility scripts | Ruff 0.16.8 for lint/format; existing mypy for application and selected operator-script types.                 |
| TypeScript, JavaScript and Svelte                                      | ESLint 10.10.0 with typescript-eslint 8.70.0 and eslint-plugin-svelte 3.23.0; svelte-check for frontend types. |
| Web code, HTML/CSS, JSON, YAML and Markdown                            | Prettier 3.9.8 with prettier-plugin-svelte 4.1.1.                                                              |
| Desktop Rust                                                           | Rust's bundled rustfmt and Clippy; CI uses Rust 1.96.0.                                                        |
| Shell scripts                                                          | ShellCheck 0.11.0 and shfmt 3.14.1.                                                                            |

Formatter/linter package releases were checked on 2026-09-18. Python/JavaScript versions are pinned and locked; Rust uses its bundled tools rather than a separate formatter package. Existing runtime/framework dependencies are not upgraded as part of formatting. Keep the shell tools aligned with the listed versions when reproducing formatting locally.

```sh
make format        # Format Python, web/config/docs, Rust and shell; no lint auto-fixes
make format-check  # Verify formatting without writing
make lint          # Python, frontend/desktop JavaScript and shell lint
make typecheck     # Existing Python and Svelte/TypeScript checks
make desktop-check # Rust Clippy + type/build checks
make check         # All of these, tests, operational syntax and frontend build
```

Prettier has one root configuration, and `.editorconfig` defines shared whitespace. Generated files, lockfiles, dependencies, local runtime data and third-party vendor assets are excluded from formatting. `make format` does not run the application, execute provider tasks or deploy anything. CI enforces formatting/linting plus the existing test/build checks; browser and live deployment acceptance remain separate.

Tool references: [Ruff](https://docs.astral.sh/ruff/), [Prettier installation/version pinning](https://prettier.io/docs/install), [Svelte ESLint support](https://sveltejs.github.io/eslint-plugin-svelte/user-guide/), and [Rust components](https://rust-lang.github.io/rustup/concepts/components.html).

The completed `next_todo.md` implementation plan and duplicate cleanup/follow-up notes were consolidated into the architecture report and Coordinator rollout guide. Operational guides, recorded evaluation results and third-party notices remain.
