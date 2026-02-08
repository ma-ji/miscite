#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <backup.tar.gz> --force" >&2
  exit 2
}

ARCHIVE="${1:-}"
FORCE="${2:-}"
if [ -z "$ARCHIVE" ]; then
  usage
fi
if [ ! -f "$ARCHIVE" ]; then
  echo "Backup archive not found: $ARCHIVE" >&2
  exit 1
fi
if [ "$FORCE" != "--force" ]; then
  usage
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "docker compose not found (install Docker + the compose plugin)." >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/miscite-restore-${STAMP}-XXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Extracting backup archive..."
tar -xzf "$ARCHIVE" -C "$TMP_DIR"

if [ ! -f "$TMP_DIR/postgres.dump" ]; then
  echo "Backup archive missing postgres.dump; cannot restore." >&2
  exit 1
fi

echo "Stopping app services..."
"${COMPOSE[@]}" stop web worker

echo "Ensuring database service is running..."
"${COMPOSE[@]}" up -d db >/dev/null

DB_USER="$("${COMPOSE[@]}" exec -T db sh -lc 'printf "%s" "$POSTGRES_USER"')"
DB_NAME="$("${COMPOSE[@]}" exec -T db sh -lc 'printf "%s" "$POSTGRES_DB"')"

if [ -z "$DB_USER" ] || [ -z "$DB_NAME" ]; then
  echo "Unable to resolve POSTGRES_USER/POSTGRES_DB from running db service." >&2
  exit 1
fi

mkdir -p ./data
PAYLOAD_BACKUP="./data.payload.bak.${STAMP}"
mkdir -p "$PAYLOAD_BACKUP"
shopt -s nullglob dotglob
for entry in ./data/*; do
  base="$(basename "$entry")"
  if [ "$base" = "postgres" ]; then
    continue
  fi
  mv "$entry" "$PAYLOAD_BACKUP"/
done
shopt -u nullglob dotglob

if [ -d "$TMP_DIR/data" ]; then
  shopt -s nullglob dotglob
  for entry in "$TMP_DIR/data"/*; do
    base="$(basename "$entry")"
    if [ "$base" = "postgres" ]; then
      continue
    fi
    cp -a "$entry" ./data/
  done
  shopt -u nullglob dotglob
fi

echo "Restoring PostgreSQL database (${DB_NAME})..."
if ! "${COMPOSE[@]}" exec -T db pg_restore \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges < "$TMP_DIR/postgres.dump"; then
  echo "Database restore failed. Previous non-postgres payload moved to ${PAYLOAD_BACKUP}." >&2
  exit 1
fi

echo "Re-applying migrations (if needed)..."
"${COMPOSE[@]}" run --rm migrate

echo "Starting services..."
"${COMPOSE[@]}" up -d web worker

echo "Restore complete."
