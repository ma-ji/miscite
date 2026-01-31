#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-miscite.review}"
UPSTREAM="${UPSTREAM:-http://127.0.0.1:8000}"
CLIENT_MAX_BODY_SIZE="${CLIENT_MAX_BODY_SIZE:-10m}"
PROXY_READ_TIMEOUT_SECONDS="${PROXY_READ_TIMEOUT_SECONDS:-3600}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

install_nginx() {
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -y
    $SUDO apt-get install -y nginx
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y nginx
  elif command -v yum >/dev/null 2>&1; then
    $SUDO yum install -y nginx
  else
    echo "Unsupported distro: install nginx manually." >&2
    exit 1
  fi
}

write_config() {
  local config_path
  local use_sites

  if command -v apt-get >/dev/null 2>&1; then
    use_sites="true"
    config_path="/etc/nginx/sites-available/${DOMAIN}"
  else
    use_sites="false"
    config_path="/etc/nginx/conf.d/${DOMAIN}.conf"
  fi

  $SUDO tee "${config_path}" >/dev/null <<EOF
server {
  server_name ${DOMAIN};
  listen 80;

  client_max_body_size ${CLIENT_MAX_BODY_SIZE};

  # Server-sent events (progress streaming): disable buffering and allow long reads.
  location ~* ^/api/(jobs|reports)/.+/stream$ {
    proxy_pass ${UPSTREAM};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header X-Forwarded-Host \$host;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout ${PROXY_READ_TIMEOUT_SECONDS}s;
    proxy_send_timeout ${PROXY_READ_TIMEOUT_SECONDS}s;
  }

  location / {
    proxy_pass ${UPSTREAM};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header X-Forwarded-Host \$host;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
  }
}
EOF

  if [ "${use_sites}" = "true" ]; then
    $SUDO ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
    if [ -e /etc/nginx/sites-enabled/default ]; then
      $SUDO mv /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/default.bak
    fi
  fi
}

open_firewall() {
  if command -v firewall-cmd >/dev/null 2>&1; then
    $SUDO firewall-cmd --zone=public --add-service http
    $SUDO firewall-cmd --zone=public --add-service http --permanent
  else
    echo "firewall-cmd not found; open port 80 in your firewall manually."
  fi
}

install_nginx
write_config
open_firewall

$SUDO systemctl enable --now nginx
$SUDO nginx -t
$SUDO systemctl reload nginx

echo "nginx installed and configured for http://${DOMAIN} on port 80."
