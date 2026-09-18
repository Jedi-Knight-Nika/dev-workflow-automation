#!/bin/sh
# Start the single local application and its private monitoring services.
set -eu
mode="${AEW_START_MODE:-full}"
build=true
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode)
      [ "$#" -ge 2 ] || {
        echo "--mode requires console, execution, or full" >&2
        exit 2
      }
      mode="$2"
      shift 2
      ;;
    --no-build)
      build=false
      shift
      ;;
    *)
      echo "Usage: $0 [--mode console|execution|full] [--no-build]" >&2
      exit 2
      ;;
  esac
done
case "$mode" in
  console | execution | full) ;;
  *)
    echo "Unknown startup mode: $mode" >&2
    exit 2
    ;;
esac
cd "$(dirname "$0")/.."
[ -f .env ] || {
  echo "Configure .env first. See docs/guide.md." >&2
  exit 1
}
set -- docker compose --env-file .env -p autonomous-engineering-worker -f compose.yaml
if [ "$mode" != console ]; then
  set -- "$@" -f deploy/compose.execution.yaml
fi
if [ "$mode" = full ]; then
  set -- "$@" -f deploy/compose.observability.yaml
  if [ "$(uname -s)" = Darwin ]; then
    set -- "$@" -f deploy/compose.observability.desktop.yaml
  fi
  set -- "$@" --profile alerts
fi
set -- "$@" up -d --wait
if [ "$build" = true ]; then
  set -- "$@" --build
else
  set -- "$@" --no-build
fi
exec "$@"
