#!/usr/bin/env bash
set -euo pipefail
task="$1"
[[ "$task" =~ ^[a-f0-9]{32}$ ]]
arn="arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$task"
for name in valkey backend celery-beat; do
  c="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$arn" --filter "label=com.amazonaws.ecs.container-name=$name")"
  if [[ "$c" =~ ^[a-f0-9]{12,64}$ ]]; then
    if [[ "$name" == valkey ]]; then docker exec "$c" valkey-cli CLIENT UNPAUSE >/dev/null; else docker unpause "$c" >/dev/null 2>&1 || true; fi
  fi
done
