#!/usr/bin/env bash
set -euo pipefail

# One-shot bootstrap for Ubuntu 22.04+ (Docker + Caddy + systemd).
#
# Usage:
#   DOMAIN=miscite.review APP_DIR=/opt/miscite REPO_URL=https://github.com/ma-ji/miscite bash scripts/bootstrap-vps-ubuntu.sh

DOMAIN="${DOMAIN:-miscite.review}"
APP_DIR="${APP_DIR:-/opt/miscite}"
REPO_URL="${REPO_URL:-https://github.com/ma-ji/miscite}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi
RUN_USER="${SUDO_USER:-${USER:-$(id -un)}}"
RUN_GROUP="$(id -gn "$RUN_USER")"
RUN_AS=()
if [ "$(id -u)" -eq 0 ] && [ "$RUN_USER" != "root" ]; then
  RUN_AS=(sudo -u "$RUN_USER")
fi

is_tty() {
  [ -t 0 ]
}

prompt_choice() {
  local prompt="$1"
  local default="$2"
  local choice=""
  if is_tty; then
    read -r -p "${prompt} " choice
  fi
  echo "${choice:-$default}"
}

echo "==> Installing base packages..."
$SUDO apt-get update -y
$SUDO apt-get install -y git curl ufw

if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Cloning repo to $APP_DIR"
  $SUDO mkdir -p "$APP_DIR"
  $SUDO chown -R "$RUN_USER":"$RUN_GROUP" "$APP_DIR"
  "${RUN_AS[@]}" git clone "$REPO_URL" "$APP_DIR"
else
  echo "==> Updating repo in $APP_DIR"
  $SUDO chown -R "$RUN_USER":"$RUN_GROUP" "$APP_DIR"
  "${RUN_AS[@]}" git -C "$APP_DIR" pull --ff-only
fi

cd "$APP_DIR"

echo "==> Installing Docker (Ubuntu)..."
bash scripts/install-docker-ubuntu.sh

DOCKER=(docker)
if [ "$(id -u)" -ne 0 ] && ! docker ps >/dev/null 2>&1; then
  DOCKER=("$SUDO" docker)
fi

echo "==> Ensuring .env exists..."
if [ ! -f .env ]; then
  "${RUN_AS[@]}" cp .env.example .env
fi

echo "==> Applying domain to Caddyfile..."
if grep -q "^miscite.review {" deploy/Caddyfile; then
  "${RUN_AS[@]}" sed -i "s/^miscite.review {/${DOMAIN} {/" deploy/Caddyfile
fi

echo "==> Checking required secrets..."
missing=()
for key in OPENROUTER_API_KEY MISCITE_MAILGUN_API_KEY MISCITE_MAILGUN_DOMAIN MISCITE_MAILGUN_SENDER MISCITE_TURNSTILE_SITE_KEY MISCITE_TURNSTILE_SECRET_KEY; do
  val="$(grep -E "^${key}=" .env | tail -n1 | cut -d= -f2- || true)"
  if [ -z "${val}" ]; then
    missing+=("$key")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "Missing required secrets in .env: ${missing[*]}" >&2
  echo "Edit $APP_DIR/.env and re-run this script." >&2
  exit 1
fi

echo "==> Data setup..."
DATA_DIR="$APP_DIR/data"
DB_PATH="$DATA_DIR/miscite.db"
UPLOAD_DIR="$DATA_DIR/uploads"

choice="fresh"
if [ -e "$DB_PATH" ] || [ -d "$UPLOAD_DIR" ]; then
  choice="existing"
fi
default_choice="$choice"
choice="$(prompt_choice "Use existing data or start fresh? [existing/fresh] (default: ${default_choice})" "$default_choice")"
choice="$(printf '%s' "$choice" | tr '[:upper:]' '[:lower:]')"
if [ "$choice" != "existing" ] && [ "$choice" != "fresh" ]; then
  echo "Unknown choice '${choice}', defaulting to ${default_choice}."
  choice="$default_choice"
fi

if [ "$choice" = "existing" ]; then
  echo "Place your existing DB at: ${DB_PATH}"
  echo "Place your uploads at:   ${UPLOAD_DIR}"
  if [ ! -f "$DB_PATH" ] || [ ! -d "$UPLOAD_DIR" ]; then
    if is_tty; then
      read -r -p "Press Enter once files are in place (or type 'q' to quit): " reply
      if [ "${reply:-}" = "q" ]; then
        exit 1
      fi
    else
      echo "Missing ${DB_PATH} or ${UPLOAD_DIR}. Move files into place and re-run." >&2
      exit 1
    fi
  fi
  if [ ! -f "$DB_PATH" ] || [ ! -d "$UPLOAD_DIR" ]; then
    echo "Missing ${DB_PATH} or ${UPLOAD_DIR}. Move files into place and re-run." >&2
    exit 1
  fi
else
  if [ -d "$DATA_DIR" ] && [ -n "$(ls -A "$DATA_DIR" 2>/dev/null || true)" ]; then
    echo "Data directory is not empty: ${DATA_DIR}"
    if is_tty; then
      move_choice="$(prompt_choice "Move existing data to ${DATA_DIR}.bak.<timestamp>? [y/N]" "n")"
      if [ "$move_choice" = "y" ] || [ "$move_choice" = "Y" ]; then
        stamp="$(date -u +%Y%m%dT%H%M%SZ)"
        $SUDO mv "$DATA_DIR" "${DATA_DIR}.bak.${stamp}"
      else
        echo "Refusing to start fresh with non-empty data dir." >&2
        exit 1
      fi
    else
      echo "Non-interactive run with non-empty data dir. Move it aside and re-run." >&2
      exit 1
    fi
  fi
fi

echo "==> Creating data dir..."
"${RUN_AS[@]}" mkdir -p data data/uploads
# Ensure container user (uid 1000) can write SQLite DB + uploads.
$SUDO chown -R 1000:1000 data

echo "==> Configuring firewall (UFW)..."
$SUDO ufw allow OpenSSH
$SUDO ufw allow 80/tcp
$SUDO ufw allow 443/tcp
$SUDO ufw --force enable

echo "==> Starting services (web + worker + caddy)..."
"${DOCKER[@]}" compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build

echo "==> Installing systemd unit..."
SERVICE_SRC="deploy/miscite.service"
SERVICE_TMP="/tmp/miscite.service"
sed -e "s|^WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" \
  -e "s|^Environment=.*COMPOSE_FILES=.*|Environment=\"COMPOSE_FILES=-f docker-compose.yml -f docker-compose.caddy.yml\"|" \
  "$SERVICE_SRC" > "$SERVICE_TMP"
$SUDO mv "$SERVICE_TMP" /etc/systemd/system/miscite.service
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now miscite

echo "==> Done."
echo "Check readiness: curl -fsS https://${DOMAIN}/readyz"
