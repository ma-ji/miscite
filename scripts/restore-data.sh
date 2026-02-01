#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <backup.tar.gz> [--force]" >&2
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
if [ -n "$FORCE" ] && [ "$FORCE" != "--force" ]; then
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

if [ -d "./data" ] && [ -n "$(ls -A ./data 2>/dev/null || true)" ] && [ "$FORCE" != "--force" ]; then
  echo "Refusing to restore: ./data is non-empty. Re-run with --force." >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

echo "Stopping services..."
"${COMPOSE[@]}" stop web worker

if [ -d "./data" ] && [ -n "$(ls -A ./data 2>/dev/null || true)" ]; then
  echo "Moving existing data to ./data.bak.${STAMP}"
  mv ./data "./data.bak.${STAMP}"
fi

echo "Restoring from: ${ARCHIVE}"
tar -xzf "$ARCHIVE" -C "$ROOT_DIR"

echo "Starting services..."
"${COMPOSE[@]}" start web worker

echo "Restore complete."
