#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/miscite}"
BACKUP_ON_CALENDAR="${BACKUP_ON_CALENDAR:-daily}"
BACKUP_RANDOM_DELAY_SEC="${BACKUP_RANDOM_DELAY_SEC:-900}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SERVICE_SRC="$ROOT_DIR/deploy/miscite-backup.service"
TIMER_SRC="$ROOT_DIR/deploy/miscite-backup.timer"
SERVICE_TMP="/tmp/miscite-backup.service"
TIMER_TMP="/tmp/miscite-backup.timer"

sed \
  -e "s|^WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" \
  -e "s|^Environment=\"OUT_DIR=.*|Environment=\"OUT_DIR=${APP_DIR}/backups\"|" \
  -e "s|^Environment=\"KEEP_DAYS=.*|Environment=\"KEEP_DAYS=${BACKUP_KEEP_DAYS}\"|" \
  "$SERVICE_SRC" > "$SERVICE_TMP"

sed \
  -e "s|^OnCalendar=.*|OnCalendar=${BACKUP_ON_CALENDAR}|" \
  -e "s|^RandomizedDelaySec=.*|RandomizedDelaySec=${BACKUP_RANDOM_DELAY_SEC}|" \
  "$TIMER_SRC" > "$TIMER_TMP"

$SUDO mv "$SERVICE_TMP" /etc/systemd/system/miscite-backup.service
$SUDO mv "$TIMER_TMP" /etc/systemd/system/miscite-backup.timer
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now miscite-backup.timer

echo "Installed backup timer:"
echo "  service: /etc/systemd/system/miscite-backup.service"
echo "  timer:   /etc/systemd/system/miscite-backup.timer"
echo "  schedule: ${BACKUP_ON_CALENDAR}"
