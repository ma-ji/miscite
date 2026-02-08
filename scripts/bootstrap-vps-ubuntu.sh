#!/usr/bin/env bash
set -euo pipefail

# One-shot bootstrap for Ubuntu 22.04+ (Docker + Caddy + PostgreSQL + systemd).
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

escape_sed() {
  printf '%s' "$1" | sed -e 's/[\\/&]/\\&/g'
}

env_get() {
  local key="$1"
  grep -E "^${key}=" .env | tail -n1 | cut -d= -f2- || true
}

env_set() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(escape_sed "$value")"
  if grep -qE "^${key}=" .env; then
    sed -i "s/^${key}=.*/${key}=${escaped}/" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

generate_password() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
    return 0
  fi
  date -u +%s%N | sha256sum | cut -c1-48
}

ensure_postgres_env() {
  local db_name db_user db_password db_host db_port db_url

  db_name="$(env_get POSTGRES_DB)"
  db_user="$(env_get POSTGRES_USER)"
  db_password="$(env_get POSTGRES_PASSWORD)"
  db_host="$(env_get POSTGRES_HOST)"
  db_port="$(env_get POSTGRES_PORT)"

  if [ -z "$db_name" ]; then
    db_name="miscite"
  fi
  if [ -z "$db_user" ]; then
    db_user="miscite"
  fi
  if [ -z "$db_password" ]; then
    db_password="$(generate_password)"
    echo "Generated POSTGRES_PASSWORD in .env"
  fi
  if [ -z "$db_host" ]; then
    db_host="db"
  fi
  if [ -z "$db_port" ]; then
    db_port="5432"
  fi

  env_set POSTGRES_DB "$db_name"
  env_set POSTGRES_USER "$db_user"
  env_set POSTGRES_PASSWORD "$db_password"
  env_set POSTGRES_HOST "$db_host"
  env_set POSTGRES_PORT "$db_port"

  db_url="postgresql+psycopg://${db_user}:${db_password}@${db_host}:${db_port}/${db_name}"
  env_set MISCITE_DB_URL "$db_url"
}

check_missing_env() {
  missing=()
  for key in OPENROUTER_API_KEY MISCITE_MAILGUN_API_KEY MISCITE_MAILGUN_DOMAIN MISCITE_MAILGUN_SENDER MISCITE_TURNSTILE_SITE_KEY MISCITE_TURNSTILE_SECRET_KEY; do
    val="$(grep -E "^${key}=" .env | tail -n1 | cut -d= -f2- || true)"
    if [ -z "${val}" ]; then
      missing+=("$key")
    fi
  done
}

wait_for_env_ready() {
  while true; do
    check_missing_env
    if [ "${#missing[@]}" -eq 0 ]; then
      return 0
    fi
    echo "Edit $APP_DIR/.env and set required secrets:"
    printf '  - %s\n' "${missing[@]}"
    if is_tty; then
      read -r -p "Press Enter to re-check .env (or type 'q' to quit): " reply
      if [ "${reply:-}" = "q" ]; then
        exit 1
      fi
    else
      echo "Missing required secrets in .env: ${missing[*]}" >&2
      echo "Edit $APP_DIR/.env and re-run this script." >&2
      exit 1
    fi
  done
}

wait_for_existing_data() {
  while true; do
    if [ -d "$PGDATA_DIR" ] && [ -d "$UPLOAD_DIR" ]; then
      return 0
    fi
    echo "Place your PostgreSQL data dir at: ${PGDATA_DIR}"
    echo "Place your uploads at:   ${UPLOAD_DIR}"
    if is_tty; then
      read -r -p "Press Enter to re-check (or type 'q' to quit): " reply
      if [ "${reply:-}" = "q" ]; then
        exit 1
      fi
    else
      echo "Missing ${PGDATA_DIR} or ${UPLOAD_DIR}. Move files into place and re-run." >&2
      exit 1
    fi
  done
}

echo "==> Installing base packages..."
$SUDO apt-get update -y
$SUDO apt-get install -y git curl ufw openssl

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
ensure_postgres_env
$SUDO chown "$RUN_USER":"$RUN_GROUP" .env
wait_for_env_ready

echo "==> Applying domain to Caddyfile..."
if grep -q "^miscite.review {" deploy/Caddyfile; then
  "${RUN_AS[@]}" sed -i "s/^miscite.review {/${DOMAIN} {/" deploy/Caddyfile
fi

echo "==> Data setup..."
DATA_DIR="$APP_DIR/data"
UPLOAD_DIR="$DATA_DIR/uploads"
PGDATA_DIR="$DATA_DIR/postgres"
BACKUP_DIR="$APP_DIR/backups"

choice="fresh"
if [ -d "$PGDATA_DIR" ] && [ -n "$(ls -A "$PGDATA_DIR" 2>/dev/null || true)" ]; then
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
  wait_for_existing_data
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

echo "==> Creating storage dirs..."
"${RUN_AS[@]}" mkdir -p data/uploads data/postgres backups
$SUDO chown -R 1000:1000 "$DATA_DIR" "$BACKUP_DIR"
$SUDO chmod -R u+rwX "$DATA_DIR" "$BACKUP_DIR"
$SUDO chmod 700 "$PGDATA_DIR" || true

echo "==> Configuring firewall (UFW)..."
$SUDO ufw allow OpenSSH
$SUDO ufw allow 80/tcp
$SUDO ufw allow 443/tcp
$SUDO ufw --force enable

echo "==> Starting services (db + migrate + web + worker + caddy)..."
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

echo "==> Installing backup timer..."
APP_DIR="$APP_DIR" \
  BACKUP_ON_CALENDAR="${BACKUP_ON_CALENDAR:-daily}" \
  BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}" \
  BACKUP_RANDOM_DELAY_SEC="${BACKUP_RANDOM_DELAY_SEC:-900}" \
  bash scripts/install-backup-timer.sh

echo "==> Done."
echo "Check readiness: curl -fsS https://${DOMAIN}/readyz"
