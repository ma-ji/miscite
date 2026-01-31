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
OUT_PATH="${OUT_DIR%/}/miscite-data-${STAMP}.tar.gz"

mkdir -p "$OUT_DIR"

echo "Stopping services..."
"${COMPOSE[@]}" stop web worker

echo "Creating backup: ${OUT_PATH}"
tar -czf "$OUT_PATH" --exclude="./data/cache" data

echo "Starting services..."
"${COMPOSE[@]}" start web worker

echo "Done: ${OUT_PATH}"
