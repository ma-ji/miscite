#!/usr/bin/env bash
set -euo pipefail

# Install Docker Engine + Compose plugin on Ubuntu 22.04+
# Ref: https://docs.docker.com/engine/install/ubuntu/

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

$SUDO apt-get update -y
$SUDO apt-get install -y ca-certificates curl gnupg lsb-release

$SUDO install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
$SUDO chmod a+r /etc/apt/keyrings/docker.gpg

UBUNTU_CODENAME="$(lsb_release -cs)"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  ${UBUNTU_CODENAME} stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null

$SUDO apt-get update -y
$SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

$SUDO systemctl enable --now docker

if [ "$(id -u)" -ne 0 ]; then
  $SUDO usermod -aG docker "$USER"
  echo "Added $USER to the docker group. Log out/in to apply."
fi

echo "Docker install complete."
