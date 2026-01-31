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

echo "==> Installing base packages..."
$SUDO apt-get update -y
$SUDO apt-get install -y git curl ufw

if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Cloning repo to $APP_DIR"
  $SUDO mkdir -p "$(dirname "$APP_DIR")"
  $SUDO git clone "$REPO_URL" "$APP_DIR"
  $SUDO chown -R "$USER":"$USER" "$APP_DIR"
else
  echo "==> Updating repo in $APP_DIR"
  $SUDO git -C "$APP_DIR" pull --ff-only
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
  cp .env.example .env
fi

echo "==> Applying domain to Caddyfile..."
if grep -q "^miscite.review {" deploy/Caddyfile; then
  $SUDO sed -i "s/^miscite.review {/${DOMAIN} {/" deploy/Caddyfile
fi

echo "==> Checking required secrets..."
missing=()
for key in OPENROUTER_API_KEY MISCITE_MAILGUN_API_KEY MISCITE_MAILGUN_DOMAIN MISCITE_MAILGUN_SENDER; do
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

echo "==> Creating data dir..."
mkdir -p data

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
sed "s|^WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" "$SERVICE_SRC" > "$SERVICE_TMP"
$SUDO mv "$SERVICE_TMP" /etc/systemd/system/miscite.service
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now miscite

echo "==> Done."
echo "Check readiness: curl -fsS https://${DOMAIN}/readyz"
