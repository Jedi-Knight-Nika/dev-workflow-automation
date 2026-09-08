# Private V2.1 monitoring

The optional overlay never resets the application database, modifies budgets or
grants merge authority. Migrate a restored backup first. Disable the supporting
features to roll back the application; keep the additive history tables.

## Configuration

Use the same base/V2 Compose files and project as execution, adding
`deploy/compose.observability.yaml` last. Provide these operator-owned settings:

```
OBSERVABILITY_CONFIG_ROOT=/absolute/repository/monitoring
OBSERVABILITY_ENABLED=true
OBSERVABILITY_HOST_ID=server-1
OBSERVABILITY_COMPOSE_PROJECT=autonomous-engineering-worker
METRICS_TOKEN_FILE=/protected/secrets/metrics-token
OBSERVABILITY_ALERT_TOKEN_FILE=/protected/secrets/alert-token
POSTGRES_MONITOR_PASSWORD_FILE=/protected/secrets/postgres-monitor-password
OBSERVABILITY_RETENTION_DAYS=30
OBSERVABILITY_RETENTION_SIZE=5GB
FORECASTS_ENABLED=false
FORECAST_MIN_SAMPLES=5
```

Use independent random 32+ character token files readable by the relevant
container UIDs (Prometheus/exporters commonly 65534). Never commit secrets.
Monitoring images are version-pinned; override their `*_IMAGE` variables with
verified immutable digests for the production host. All new monitoring services
have CPU/memory/PID limits and no published ports. Do not route exporters through
Caddy. The controller alone observes Docker events. cAdvisor is separately trusted
host infrastructure and has sensitive mounts; deploy it only on the trusted host.

Provision a dedicated PostgreSQL LOGIN role `aew_monitor` with a generated
password matching its secret file, CONNECT to the application database, and
membership in `pg_monitor`. Do not grant application table writes or use the app
database superuser. This is an explicit DBA deployment step, not an app migration.
Password setup should use an interactive client or a protected provisioning tool,
never shell history. Exporter configuration uses `DATA_SOURCE_PASS_FILE`.

Use `--profile alerts` to enable Alertmanager. Its webhook is token-authenticated
and blocked at public Caddy ingress. Annotation/free-text/secret labels are dropped
before incident persistence. The monitoring settings form persists CPU/RAM/disk
and queue-age thresholds; application metrics expose them to the rules in
`prometheus/rules/operations.yml`. Threshold changes take effect after scraping;
changes to the rule definitions themselves require a Prometheus reload.

Apply additive migrations through `0003_operational_configuration`. The settings
form also saves refresh, forecasting, alert ingestion and collection preferences.
It can disable application-side querying and collection, but cannot install or
stop Docker exporter services.
Retention changes are saved as desired settings and shown as pending until the
operator updates the deployment environment and recreates Prometheus. Secrets,
targets and production resource limits remain operator-managed.

## Linux vs local Docker Desktop

Linux host metrics are the production target. On Docker Desktop, cAdvisor's
`/dev/kmsg`/disk mounts and root propagation can require a host-specific overlay.
VM metrics are development diagnostics, not macOS host measurements. Do not remove
execution isolation to make an exporter work. Keep unsupported collectors disabled
and label their data unavailable. Default blackbox targets probe internal frontend
and backend readiness/liveness; add a verified operator-managed HTTPS ingress
probe (including a dedicated probe credential if needed) for end-to-end uptime.

For the configured local instance, run `sh scripts/local-v21.sh` from the
repository. One ignored `.env` contains native runtime and monitoring configuration.
The script selects the Desktop collector overlay on macOS. The current local
`.env` also defines `COMPOSE_FILE` and `COMPOSE_PROFILES`, so plain `docker compose
up -d --build` starts the same complete app. All application contexts use the one
`engineering_worker` database; Prometheus retains only operational time series.
Set `OBSERVABILITY_POSTGRES_DB` when the native API database differs from the
PostgreSQL container's original `POSTGRES_DB` initialization name.

## Acceptance (must be recorded, not inferred)

1. Test `0001 -> 0002 -> 0003` on a restored database and compare existing records.
2. Validate Compose and Prometheus/Alertmanager configuration using their tools.
3. Inspect target health inside Prometheus; never publish monitoring ports.
4. Run an unpaid isolated container, verify binding, event dedup and summary.
5. Stop Prometheus/exporters during an unpaid validation; execution must continue.
6. Test alert firing/resolution, missing samples and short-lived runners.
7. Measure the same workload with monitoring enabled/disabled; retain results.
8. Only then enable advisory forecasts and run authorized ticket benchmarks.

Retention time and size bound TSDB retention, not the entire filesystem. Reserve
headroom for WAL/head blocks and other application data. No raw samples are copied
to PostgreSQL. Historical resource gaps remain unknown; summaries report coverage.

No Grafana, monitoring SaaS, AI forecasting, ML model or resource admission policy
is required. Grafana can be added later as a private operator-only service.
