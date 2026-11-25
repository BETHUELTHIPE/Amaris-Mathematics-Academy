#!/usr/bin/env bash
set -euo pipefail

address="$1"
mode="$2"
[[ "$address" == 16.171.164.5 ]]
root=/opt/amaris-staging/vpc
nginx=/opt/amaris-staging/nginx
backup="$root/public-proxy-backup"

restore() {
  test -s "$backup/default.conf"
  test -s "$backup/backend-proxy.inc"
  systemctl disable --now amaris-private-task-gateway.timer >/dev/null 2>&1 || true
  systemctl stop amaris-private-task-gateway.service >/dev/null 2>&1 || true
  cp "$backup/default.conf" "$nginx/default.conf"
  cp "$backup/backend-proxy.inc" "$nginx/backend-proxy.inc"
  docker exec amaris-gateway nginx -t >/dev/null
  docker exec amaris-gateway nginx -s reload >/dev/null
  rm -f "$nginx/amaris-private-task.conf"
}

if [[ "$mode" == rollback ]]; then
  restore
  echo 'The HTTPS gateway is back on the previous ECS service.'
  exit 0
fi
[[ "$mode" == switch ]]
private_ip="$3"
[[ "$private_ip" =~ ^10\.86\.0\.[0-9]+$ ]]
install -d -m 0700 "$backup"
if ! grep -Fq 'add_header X-Amaris-Network private-vpc always;' "$nginx/default.conf"; then
  grep -Eiq 'proxy_pass http://172\.[0-9.]+:13000;' "$nginx/default.conf"
  grep -Eiq 'proxy_pass http://172\.[0-9.]+:18000;' "$nginx/backend-proxy.inc"
  cp "$nginx/default.conf" "$backup/default.conf"
  cp "$nginx/backend-proxy.inc" "$backup/backend-proxy.inc"
fi

cat > "$root/refresh-gateway.sh" <<'REFRESH'
#!/usr/bin/env bash
set -euo pipefail

address=16.171.164.5
nginx=/opt/amaris-staging/nginx
candidate="${1:-}"
exec 9>/run/amaris-private-task-gateway.lock
flock -n 9 || exit 0
if [[ -z "$candidate" ]]; then
  id="$(docker ps --filter label=com.amazonaws.ecs.task-definition-family=amaris-ecs-staging-private-web \
    --filter label=com.amazonaws.ecs.container-name=frontend --filter health=healthy --format '{{.ID}}')"
  [[ "$id" =~ ^[a-f0-9]{12,64}$ ]] || exit 0
  pid="$(docker inspect --format '{{.State.Pid}}' "$id")"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || exit 0
  candidate="$(nsenter --target "$pid" --net ip -4 -o addr show scope global | awk 'NR==1 {split($4, addr, "/"); print addr[1]}')"
fi
[[ "$candidate" =~ ^10\.86\.0\.([0-9]{3})$ ]]
[[ "${BASH_REMATCH[1]}" -ge 129 && "${BASH_REMATCH[1]}" -le 254 ]]
conf="$nginx/amaris-private-task.conf"
if [[ -f "$conf" ]] && grep -Fxq "upstream amaris_private_frontend { server $candidate:3000; }" "$conf"; then
  exit 0
fi
docker exec amaris-gateway wget -T 8 -qO- "http://$candidate:3000/health/ready" \
  | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'
docker exec amaris-gateway wget -T 8 -qO- --header "Host: $address" --header 'X-Forwarded-Proto: https' \
  "http://$candidate:8000/health/ready/" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ready"'

previous="$(mktemp)"
next="$(mktemp "$nginx/.amaris-private-task.XXXXXX")"
trap 'rm -f "$previous" "$next"' EXIT
if [[ -f "$conf" ]]; then cp "$conf" "$previous"; fi
{
  printf 'upstream amaris_private_frontend { server %s:3000; }\n' "$candidate"
  printf 'upstream amaris_private_backend { server %s:8000; }\n' "$candidate"
} > "$next"
chmod 644 "$next"
mv "$next" "$conf"
if ! docker exec amaris-gateway nginx -t >/dev/null || ! docker exec amaris-gateway nginx -s reload >/dev/null; then
  if [[ -s "$previous" ]]; then cp "$previous" "$conf"; else rm -f "$conf"; fi
  exit 1
fi
REFRESH
chmod 700 "$root/refresh-gateway.sh"
trap 'restore || true' ERR
"$root/refresh-gateway.sh" "$private_ip"
sed -E -e 's|proxy_pass http://172\.[0-9.]+:13000;|proxy_pass http://amaris_private_frontend;|' \
  -e '/add_header X-Amaris-Compute/a\    add_header X-Amaris-Network private-vpc always;' "$backup/default.conf" > "$nginx/default.conf"
sed -E 's|proxy_pass http://172\.[0-9.]+:18000;|proxy_pass http://amaris_private_backend;|' \
  "$backup/backend-proxy.inc" > "$nginx/backend-proxy.inc"
docker exec amaris-gateway nginx -t >/dev/null
docker exec amaris-gateway nginx -s reload >/dev/null
for attempt in {1..12}; do
  headers="$(curl -fSs -D - -o /dev/null --max-time 8 --resolve "$address:443:127.0.0.1" \
    "https://$address/health/ready" || true)"
  if grep -Eiq '^X-Amaris-Network: private-vpc' <<< "$headers"; then break; fi
  sleep 1
done
grep -Eiq '^X-Amaris-Network: private-vpc' <<< "$headers"
cat > /etc/systemd/system/amaris-private-task-gateway.service <<UNIT
[Unit]
Description=Refresh the Amaris HTTPS gateway from its healthy private ECS task
Requires=docker.service
After=docker.service ecs.service

[Service]
Type=oneshot
ExecStart=$root/refresh-gateway.sh
UNIT
cat > /etc/systemd/system/amaris-private-task-gateway.timer <<'UNIT'
[Unit]
Description=Follow ECS private task address changes

[Timer]
OnBootSec=20sec
OnUnitActiveSec=15sec
AccuracySec=2sec

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now amaris-private-task-gateway.timer >/dev/null
trap - ERR
echo 'The public HTTPS gateway now uses the verified private ECS task address.'
