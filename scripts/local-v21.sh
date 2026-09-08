#!/bin/sh
# One local configuration and one application database.
set -eu
cd "$(dirname "$0")/.."
[ -f .env ] || {
  echo "Configure .env first. See monitoring/README.md." >&2
  exit 1
}
set -- docker compose --env-file .env \
  -p autonomous-engineering-worker -f compose.yaml -f deploy/compose.v2.yaml \
  -f deploy/compose.observability.yaml
if [ "$(uname -s)" = Darwin ]; then
  set -- "$@" -f deploy/compose.observability.desktop.yaml
fi
exec "$@" --profile alerts up -d --build --wait
