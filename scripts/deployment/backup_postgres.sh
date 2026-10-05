#!/usr/bin/env bash
# EcoTrace India — PostgreSQL backup (P9.8).
#
# Takes a real pg_dump (custom format, suitable for pg_restore) of the
# running compose stack's database and copies it to the host. Genuinely
# rehearsed against the live P9.8 stack — see reports/P9_8_*.md for the
# real backup + restore drill this script's approach was based on.
#
# Usage:
#   scripts/deployment/backup_postgres.sh [output-dir]
#
# Requires: the `postgres` service from docker-compose.yml running as
# container `ecotrace-postgres` (the default `docker compose up` name).
# Reads POSTGRES_USER/POSTGRES_DB from the environment if set, otherwise
# falls back to the same local-dev defaults docker-compose.yml itself uses.

set -euo pipefail

CONTAINER="ecotrace-postgres"
DB_USER="${POSTGRES_USER:-ecotrace}"
DB_NAME="${POSTGRES_DB:-ecotrace}"
OUT_DIR="${1:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILENAME="ecotrace_${TIMESTAMP}.dump"
CONTAINER_PATH="/tmp/${FILENAME}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: container '${CONTAINER}' is not running. Start the stack with" >&2
  echo "  docker compose up -d postgres" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

echo "Backing up database '${DB_NAME}' from container '${CONTAINER}'..."
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom -f "$CONTAINER_PATH"
docker cp "${CONTAINER}:${CONTAINER_PATH}" "${OUT_DIR}/${FILENAME}"
docker exec "$CONTAINER" rm -f "$CONTAINER_PATH"

echo "Backup written to ${OUT_DIR}/${FILENAME}"
ls -la "${OUT_DIR}/${FILENAME}"
