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
cleanup() {
  if [[ "$success" == 0 ]]; then docker exec "$valkey" valkey-cli CLIENT UNPAUSE >/dev/null 2>&1 || true; fi
  docker unpause "$backend" "$beat" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/host-password --with-decryption --query Parameter.Value --output json > "$tmp/pw"
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/ca --query Parameter.Value --output json > "$tmp/ca"
jq -cn --arg ip "$ip" --slurpfile password "$tmp/pw" --slurpfile ca "$tmp/ca" '{ip:$ip,password:$password[0],ca:$ca[0]}' > "$tmp/input"
# The gateway was already closed; stop the two local producers before freezing the worker.
docker pause "$backend" "$beat" >/dev/null
docker exec -i "$worker" python -c "$migration_code" < "$tmp/input"
success=1
echo 'Source write pause is active for ten minutes; source disk retained.'
