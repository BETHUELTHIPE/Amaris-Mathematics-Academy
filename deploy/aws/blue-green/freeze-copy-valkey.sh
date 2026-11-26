#!/usr/bin/env bash
set -euo pipefail
umask 077
task="$1"
ip="$2"
[[ "$task" =~ ^[a-f0-9]{32}$ && "$ip" =~ ^10\.86\.0\.[0-9]+$ ]]
arn="arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$task"
get() { docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$arn" --filter "label=com.amazonaws.ecs.container-name=$1"; }
backend="$(get backend)"
beat="$(get celery-beat)"
worker="$(get celery-worker)"
valkey="$(get valkey)"
for c in "$backend" "$beat" "$worker" "$valkey"; do [[ "$c" =~ ^[a-f0-9]{12,64}$ ]]; done
tmp="$(mktemp -d)"
success=0
worker_pid=''
frozen=()
cleanup() {
  if [[ "$success" == 0 ]]; then docker exec "$valkey" valkey-cli CLIENT UNPAUSE >/dev/null 2>&1 || true; fi
  if [[ -n "$worker_pid" && "$(docker inspect --format '{{.State.Pid}}' "$worker" 2>/dev/null || true)" == "$worker_pid" ]]; then
    for pid in "${frozen[@]}"; do
      if docker top "$worker" -eo pid | awk 'NR>1{print $1}' | grep -Fxq "$pid"; then kill -CONT "$pid" 2>/dev/null || true; fi
    done
  fi
  docker unpause "$backend" "$beat" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/host-password --with-decryption --query Parameter.Value --output json > "$tmp/pw"
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/ca --query Parameter.Value --output json > "$tmp/ca"
jq -cn --arg ip "$ip" --slurpfile password "$tmp/pw" --slurpfile ca "$tmp/ca" '{ip:$ip,password:$password[0],ca:$ca[0]}' > "$tmp/input"
# The gateway was already closed; stop the two local producers before freezing the worker.
docker pause "$backend" "$beat" >/dev/null
docker exec -i "$worker" python - <<'PY'
import os
from pathlib import Path
for row in Path('/proc/1/environ').read_bytes().split(b'\0'):
    if row:
        key,_,value=row.decode().partition('=')
        os.environ[key]=value
from staging_celery import app
i=app.control.inspect(timeout=3)
for name in ('active','reserved','scheduled'):
    response=getattr(i,name)()
    assert response and len(response)==1 and not any(response.values()), 'Worker not drained'
print('Active, reserved and scheduled jobs all zero.')
PY
# Stop worker processes from the host namespace: PID 1 signal restrictions inside
# containers do not apply here. No migration subprocess exists at this point.
worker_pid="$(docker inspect --format '{{.State.Pid}}' "$worker")"
[[ "$worker_pid" =~ ^[1-9][0-9]+$ ]]
kill -STOP "$worker_pid"
frozen+=("$worker_pid")
mapfile -t children < <(docker top "$worker" -eo pid | awk 'NR>1{print $1}')
for pid in "${children[@]}"; do
  [[ "$pid" =~ ^[1-9][0-9]+$ ]]
  if [[ "$pid" != "$worker_pid" ]]; then kill -STOP "$pid"; frozen+=("$pid"); fi
done
for pid in "${frozen[@]}"; do grep -Eq '^State:[[:space:]]+T' "/proc/$pid/status"; done
docker exec -i "$worker" python -c "$migration_code" < "$tmp/input"
success=1
echo 'Source write pause is active for ten minutes; source disk retained.'
