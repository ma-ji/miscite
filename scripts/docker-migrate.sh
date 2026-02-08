#!/usr/bin/env bash
set -euo pipefail

is_true() {
  local raw="${1:-}"
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

echo "==> Checking migration status..."
if python -m server.migrate check; then
  echo "==> Database schema already at head."
  exit 0
else
  rc=$?
  if [ "$rc" -ne 1 ]; then
    echo "Migration check failed with exit code ${rc}." >&2
    exit "$rc"
  fi
fi

if is_true "${MISCITE_MIGRATE_BACKUP_ENABLED:-true}"; then
  case "${MISCITE_DB_URL:-}" in
    postgresql*|postgres*)
      backup_dir="${MISCITE_MIGRATE_BACKUP_DIR:-/app/backups/pre-migration}"
      retention_days="${MISCITE_MIGRATE_BACKUP_RETENTION_DAYS:-14}"
      stamp="$(date -u +%Y%m%dT%H%M%SZ)"
      backup_path="${backup_dir%/}/miscite-pre-migration-${stamp}.dump"

      mkdir -p "$backup_dir"
      export PGPASSWORD="${POSTGRES_PASSWORD:-}"
      pg_dump \
        --host="${POSTGRES_HOST:-db}" \
        --port="${POSTGRES_PORT:-5432}" \
        --username="${POSTGRES_USER:-miscite}" \
        --dbname="${POSTGRES_DB:-miscite}" \
        --format=custom \
        --no-owner \
        --no-privileges \
        --file="$backup_path"

      if [[ "$retention_days" =~ ^[0-9]+$ ]]; then
        find "$backup_dir" -type f -name "miscite-pre-migration-*.dump" -mtime "+${retention_days}" -delete || true
      fi
      echo "==> Pre-migration backup created: ${backup_path}"
      ;;
    *)
      echo "==> Skipping pre-migration backup: non-PostgreSQL MISCITE_DB_URL."
      ;;
  esac
fi

echo "==> Applying migrations..."
python -m server.migrate upgrade
echo "==> Migrations complete."
