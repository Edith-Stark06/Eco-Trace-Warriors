#!/usr/bin/env bash
# EcoTrace India — PostgreSQL restore (P9.8).
#
# Restores a backup produced by backup_postgres.sh. Deliberately requires
# an explicit --yes flag to overwrite the live database — the whole point
# of this script existing is to make restores *deliberate*, not a footgun.
# Genuinely rehearsed: dumped the live P9.8 demo database, restored it into
# a disposable database, and verified row counts and a sample row matched
# byte-for-byte (see reports/P9_8_*.md). This script performs the same
# operation the rehearsal proved works, just parameterized for reuse.
#
# Usage:
#   scripts/deployment/restore_postgres.sh <backup-file> --into <db-name> [--yes]
#
# --into <db-name>  Target database to restore into. Defaults to a new,
#                    disposable database (ecotrace_restore_<timestamp>) so
#                    an operator can verify a backup without ever touching
#                    the live database, unless they explicitly name the
#                    live one.
# --yes              Required to actually run when --into names an
#                    existing database (skips the confirmation prompt).

set -euo pipefail

CONTAINER="ecotrace-postgres"
DB_USER="${POSTGRES_USER:-ecotrace}"

BACKUP_FILE=""
TARGET_DB=""
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --into)
      TARGET_DB="$2"
      shift 2
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    *)
      BACKUP_FILE="$1"
      shift
      ;;
  esac
done

if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
  echo "ERROR: backup file not found: '${BACKUP_FILE}'" >&2
  echo "Usage: $0 <backup-file> --into <db-name> [--yes]" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: container '${CONTAINER}' is not running." >&2
  exit 1
fi

if [[ -z "$TARGET_DB" ]]; then
  TARGET_DB="ecotrace_restore_$(date -u +%Y%m%dT%H%M%SZ)"
  echo "No --into given; restoring into a new disposable database: ${TARGET_DB}"
fi

EXISTS=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}'")

if [[ "$EXISTS" == "1" && "$ASSUME_YES" != "1" ]]; then
  echo "ERROR: database '${TARGET_DB}' already exists. Pass --yes to overwrite it," >&2
  echo "or choose a different --into name to restore alongside it instead." >&2
  exit 1
fi

if [[ "$EXISTS" == "1" ]]; then
  echo "Dropping existing database '${TARGET_DB}' (--yes given)..."
  docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "DROP DATABASE \"${TARGET_DB}\";"
fi

docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE \"${TARGET_DB}\";"

CONTAINER_PATH="/tmp/$(basename "$BACKUP_FILE")"
docker cp "$BACKUP_FILE" "${CONTAINER}:${CONTAINER_PATH}"
docker exec "$CONTAINER" pg_restore -U "$DB_USER" -d "$TARGET_DB" "$CONTAINER_PATH"
docker exec "$CONTAINER" rm -f "$CONTAINER_PATH"

echo "Restored '${BACKUP_FILE}' into database '${TARGET_DB}'."
