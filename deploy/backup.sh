#!/bin/sh
set -eu

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="/backups/${timestamp}"
temporary="${destination}.incomplete"

mkdir -p "$temporary"
trap 'rm -rf "$temporary"' EXIT INT TERM

pg_dump --format=custom --file="$temporary/database.dump"
tar -C /workspaces -czf "$temporary/workspaces.tar.gz" .

pg_restore --list "$temporary/database.dump" >/dev/null
tar -tzf "$temporary/workspaces.tar.gz" >/dev/null
sha256sum "$temporary/database.dump" "$temporary/workspaces.tar.gz" \
  | sed "s#${temporary}/##" >"$temporary/SHA256SUMS"

mv "$temporary" "$destination"
trap - EXIT INT TERM

case "${BACKUP_RETENTION_DAYS}" in
  ''|*[!0-9]*)
    echo "BACKUP_RETENTION_DAYS must be a non-negative integer" >&2
    exit 1
    ;;
  *)
    find /backups -mindepth 1 -maxdepth 1 -type d \
      -mtime "+${BACKUP_RETENTION_DAYS}" -exec rm -rf -- {} +
    ;;
esac

echo "Backup created: ${destination}"
