#!/bin/sh
# Restore into a NEW empty database and empty runtime directories only.
set -eu
[ "${CONFIRM_RESTORE:-}" = RESTORE ] && [ "${CONFIRM_QUIESCENT:-}" = YES ] || {
  echo "Stop API/controller/runners and set CONFIRM_RESTORE=RESTORE and CONFIRM_QUIESCENT=YES." >&2
  exit 1
}
case "${BACKUP_SET:-}" in
  ''|*[!0-9A-Za-z-]*) echo "BACKUP_SET must be one backup directory basename" >&2; exit 1 ;;
esac
[ -n "${RESTORE_DATABASE:-}" ] || { echo "Set RESTORE_DATABASE to a new database name" >&2; exit 1; }
cd "/backups/$BACKUP_SET"
sha256sum -c SHA256SUMS
pg_restore --list database.dump >/dev/null
tar -tzf runtime.tar.gz >/dev/null
for directory in workspaces native control; do
  target="/engineering-data/$directory"
  [ ! -L "$target" ] || { echo "Refusing symlink $target" >&2; exit 1; }
  mkdir -p "$target"
  [ -z "$(ls -A "$target")" ] || { echo "Refusing nonempty $target" >&2; exit 1; }
done
# Archives must originate from our backup tool; never restore an untrusted archive.
# createdb deliberately fails when the destination already exists. No drop/truncate.
export PGDATABASE=postgres
createdb "$RESTORE_DATABASE"
pg_restore --exit-on-error --no-owner --dbname="$RESTORE_DATABASE" database.dump
tar -C /engineering-data -xzf runtime.tar.gz
echo "Restored $BACKUP_SET. Verify ownership, paths, secrets and stopped tasks before enabling execution."
