#!/bin/sh
set -eu

if [ "${CONFIRM_RESTORE}" != "RESTORE" ]; then
  echo "Refusing restore: set CONFIRM_RESTORE=RESTORE" >&2
  exit 1
fi

case "${BACKUP_SET}" in
  ????????T??????Z) ;;
  *)
    echo "BACKUP_SET must be a timestamp directory name such as 20260905T120000Z" >&2
    exit 1
    ;;
esac
case "${BACKUP_SET}" in
  *[!0-9TZ]*)
    echo "BACKUP_SET contains invalid characters" >&2
    exit 1
    ;;
esac

source_directory="/backups/${BACKUP_SET}"
for required_file in database.dump workspaces.tar.gz SHA256SUMS; do
  if [ ! -f "${source_directory}/${required_file}" ]; then
    echo "Missing ${source_directory}/${required_file}" >&2
    exit 1
  fi
done

cd "$source_directory"
sha256sum -c SHA256SUMS
pg_restore --list database.dump >/dev/null
tar -tzf workspaces.tar.gz >/dev/null

export PGDATABASE=postgres
dropdb --if-exists --force "$RESTORE_DATABASE"
createdb "$RESTORE_DATABASE"
pg_restore --exit-on-error --no-owner --dbname="$RESTORE_DATABASE" database.dump

find /workspaces -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
tar -C /workspaces -xzf workspaces.tar.gz

echo "Restore completed from ${source_directory}"
