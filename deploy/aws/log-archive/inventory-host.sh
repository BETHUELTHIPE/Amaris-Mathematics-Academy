#!/usr/bin/env bash
set -euo pipefail
echo "Host architecture: $(uname -m)"
for c in $(docker ps -q); do
  docker inspect --format '{{.Name}} cluster={{index .Config.Labels "com.amazonaws.ecs.cluster"}} component={{index .Config.Labels "com.amazonaws.ecs.container-name"}} driver={{.HostConfig.LogConfig.Type}}' "$c"
done
command -v aws || true
systemctl list-unit-files --no-legend | awk '$1 ~ /^(amaris|amazon-cloudwatch-agent)/ {print $1, $2}'
