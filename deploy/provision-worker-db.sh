#!/bin/sh
set -eu

: "${PGHOST:=postgres}"
: "${PGDATABASE:=engineering_worker}"
: "${PGUSER:=engineering_worker}"
: "${WORKER_DB_USER:?Set WORKER_DB_USER}"
: "${WORKER_DB_PASSWORD:?Set WORKER_DB_PASSWORD}"

case "$WORKER_DB_USER" in
  *[!a-zA-Z0-9_]*) echo "WORKER_DB_USER must contain only letters, numbers, and underscore" >&2; exit 2 ;;
esac

psql --set=ON_ERROR_STOP=1 \
  --set=worker_user="$WORKER_DB_USER" \
  --set=worker_password="$WORKER_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'worker_user', :'worker_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'worker_user') \gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'worker_user', :'worker_password') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'worker_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'worker_user') \gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'worker_user') \gexec
SELECT format('GRANT UPDATE ON tasks, repositories TO %I', :'worker_user') \gexec
SELECT format('GRANT INSERT ON worker_runs TO %I', :'worker_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO %I', :'worker_user') \gexec
SQL

echo "Disposable-worker database role provisioned."
