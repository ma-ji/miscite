#!/usr/bin/env bash
set -euo pipefail

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
OUT_DIR="${OUT_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
OUT_PATH="${OUT_DIR%/}/miscite-backup-${STAMP}.tar.gz"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/miscite-backup-${STAMP}-XXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$OUT_DIR"

echo "Ensuring database service is running..."
"${COMPOSE[@]}" up -d db >/dev/null

DB_USER="$("${COMPOSE[@]}" exec -T db sh -lc 'printf "%s" "$POSTGRES_USER"')"
DB_NAME="$("${COMPOSE[@]}" exec -T db sh -lc 'printf "%s" "$POSTGRES_DB"')"

if [ -z "$DB_USER" ] || [ -z "$DB_NAME" ]; then
  echo "Unable to resolve POSTGRES_USER/POSTGRES_DB from running db service." >&2
  exit 1
fi

echo "Dumping PostgreSQL database (${DB_NAME})..."
"${COMPOSE[@]}" exec -T db pg_dump \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -Fc \
  --no-owner \
  --no-privileges > "$TMP_DIR/postgres.dump"

if [ ! -s "$TMP_DIR/postgres.dump" ]; then
  echo "Database dump is empty; aborting backup." >&2
  exit 1
fi

cat > "$TMP_DIR/manifest.txt" <<EOF
created_at_utc=${STAMP}
db_engine=postgresql
db_name=${DB_NAME}
db_user=${DB_USER}
includes=postgres.dump,data_without_cache_or_pgdata
EOF

echo "Creating backup: ${OUT_PATH}"
if [ -d "./data" ]; then
  tar -czf "$OUT_PATH" \
    --exclude="./data/cache" \
    --exclude="./data/postgres" \
    data \
    -C "$TMP_DIR" postgres.dump manifest.txt
else
  tar -czf "$OUT_PATH" -C "$TMP_DIR" postgres.dump manifest.txt
fi

if [[ "$KEEP_DAYS" =~ ^[0-9]+$ ]]; then
  find "$OUT_DIR" -maxdepth 1 -type f -name "miscite-backup-*.tar.gz" -mtime "+${KEEP_DAYS}" -delete || true
fi

echo "Done: ${OUT_PATH}"
