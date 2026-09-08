#!/bin/sh
# Run only after stopping API/controller and every managed task runner.
set -eu
[ "${CONFIRM_QUIESCENT:-}" = YES ] || {
  echo "Stop API, worker and native runners, then set CONFIRM_QUIESCENT=YES." >&2
  exit 1
}
for directory in workspaces native control; do
  [ -d "/engineering-data/$directory" ] || { echo "Missing data directory: $directory" >&2; exit 1; }
done
umask 077
temporary="$(mktemp -d /backups/incomplete.XXXXXXXX)"
# Failed sets are kept for inspection, never silently deleted.
pg_dump --format=custom --file="$temporary/database.dump"
tar -C /engineering-data -czf "$temporary/runtime.tar.gz" workspaces native control
pg_restore --list "$temporary/database.dump" >/dev/null
tar -tzf "$temporary/runtime.tar.gz" >/dev/null
(cd "$temporary" && sha256sum database.dump runtime.tar.gz >SHA256SUMS)
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="/backups/${stamp}-${temporary##*.}"
mv "$temporary" "$destination"
echo "Verified backup: $destination. Protect it as credentials; retention is operator-managed."
