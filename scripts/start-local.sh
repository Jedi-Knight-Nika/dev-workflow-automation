#!/bin/sh
# Start the single local application and its private monitoring services.
set -eu
cd "$(dirname "$0")/.."
[ -f .env ] || {
  echo "Configure .env first. See PRODUCT_DESCRIPTION.md." >&2
  exit 1
}
set -- docker compose --env-file .env \
  -p autonomous-engineering-worker -f compose.yaml -f deploy/compose.execution.yaml \
  -f deploy/compose.observability.yaml
if [ "$(uname -s)" = Darwin ]; then
  set -- "$@" -f deploy/compose.observability.desktop.yaml
fi
exec "$@" --profile alerts up -d --build --wait
