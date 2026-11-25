#!/usr/bin/env bash
set -euo pipefail

[[ "$(uname -m)" == aarch64 ]]
cluster=amaris-ecs-staging
if systemctl is-active --quiet ecs; then
  grep -Fxq "ECS_CLUSTER=$cluster" /etc/ecs/ecs.config
  echo 'The existing ECS agent is configured for Amaris staging.'
  exit 0
fi
systemctl is-active --quiet docker
install -d -m 0755 /etc/ecs
if [[ -f /etc/ecs/ecs.config ]] && grep -q '^ECS_CLUSTER=' /etc/ecs/ecs.config; then
  grep -Fxq "ECS_CLUSTER=$cluster" /etc/ecs/ecs.config
fi
cat > /etc/ecs/ecs.config <<CONFIG
ECS_CLUSTER=$cluster
ECS_RESERVED_MEMORY=256
ECS_LOGLEVEL=warn
ECS_AVAILABLE_LOGGING_DRIVERS=["json-file"]
CONFIG

if ! rpm -q ecs-init >/dev/null && ! rpm -q amazon-ecs-init >/dev/null; then
  if dnf -q list --available ecs-init >/dev/null 2>&1; then
    dnf -y install ecs-init
  else
    package_dir="$(mktemp -d)"
    trap 'rm -rf -- "$package_dir"' EXIT
    package="$package_dir/amazon-ecs-init.aarch64.rpm"
    curl --proto '=https' -fSs --retry 3 --max-time 90 -o "$package" \
      https://s3.eu-central-1.amazonaws.com/amazon-ecs-agent-eu-central-1/amazon-ecs-init-latest.aarch64.rpm
    rpm -qp --queryformat '%{NAME} %{ARCH}\n' "$package" | grep -Exq '(ecs-init|amazon-ecs-init) aarch64'
    dnf -y install "$package"
  fi
fi
systemctl enable --now ecs
systemctl is-active --quiet ecs
