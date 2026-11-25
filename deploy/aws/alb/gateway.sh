#!/usr/bin/env bash
set -euo pipefail

address="$1"
[[ "$address" == 16.171.164.5 ]]
mode="$2"
root=/opt/amaris-staging/alb
nginx=/opt/amaris-staging/nginx
backup="$root/previous-gateway.conf"

restore() {
  systemctl disable --now amaris-alb-gateway.timer >/dev/null 2>&1 || true
  systemctl stop amaris-alb-gateway.service >/dev/null 2>&1 || true
  if [[ -s "$backup" ]]; then
    cp "$backup" "$nginx/default.conf"
    docker exec amaris-gateway nginx -t >/dev/null
    docker exec amaris-gateway nginx -s reload >/dev/null
  fi
  rm -f "$nginx/amaris-alb-nodes.conf"
  systemctl start amaris-private-task-gateway.timer
}

if [[ "$mode" == rollback ]]; then
  restore
  echo 'Restored the previous HTTPS route.'
  exit 0
fi
[[ "$mode" == switch ]]
alb="$3"
[[ "$alb" =~ ^app/amaris-staging-alb/[a-f0-9]+$ ]]
install -d -m 0755 "$root"
printf '%s\n' "$alb" > "$root/alb-id"
cat > "$root/refresh-gateway.sh" <<'REFRESH'
#!/usr/bin/env bash
set -euo pipefail

root=/opt/amaris-staging/alb
nginx=/opt/amaris-staging/nginx
alb="$(cat "$root/alb-id")"
exec 9>/run/amaris-alb-gateway.lock
flock -n 9 || exit 0
ips="$(aws ec2 describe-network-interfaces --region eu-north-1 \
  --filters "Name=description,Values=ELB $alb" "Name=status,Values=in-use" \
  --query 'NetworkInterfaces[].PrivateIpAddress' --output json | python3 -c '
import ipaddress, json, sys
network = ipaddress.IPv4Network("10.86.0.0/25")
addresses = sorted({ipaddress.IPv4Address(value) for value in json.load(sys.stdin)})
assert 1 <= len(addresses) <= 8 and all(addr in network for addr in addresses)
for address in addresses:
    print(address)
')"
test -n "$ips"
config="$nginx/amaris-alb-nodes.conf"
next="$(mktemp "$nginx/.amaris-alb-nodes.XXXXXX")"
previous="$(mktemp)"
trap 'rm -f "$next" "$previous"' EXIT
{
  printf 'upstream amaris_public_alb {\n'
  while IFS= read -r ip; do
    printf '    server %s:80 max_fails=1 fail_timeout=10s;\n' "$ip"
  done <<< "$ips"
  printf '}\n'
} > "$next"
chmod 644 "$next"
if [[ -f "$config" ]] && cmp -s "$next" "$config"; then exit 0; fi
if [[ -f "$config" ]]; then cp "$config" "$previous"; fi
mv "$next" "$config"
if ! docker exec amaris-gateway nginx -t >/dev/null || ! docker exec amaris-gateway nginx -s reload >/dev/null; then
  if [[ -s "$previous" ]]; then cp "$previous" "$config"; else rm -f "$config"; fi
  exit 1
fi
REFRESH
chmod 700 "$root/refresh-gateway.sh"
if ! grep -Fq 'X-Amaris-Network public-alb' "$nginx/default.conf"; then
  grep -Fq 'X-Amaris-Network private-vpc' "$nginx/default.conf"
  cp "$nginx/default.conf" "$backup"
fi
trap 'restore || true' ERR
"$root/refresh-gateway.sh"
healthy_nodes=0
while read -r keyword node extra; do
  [[ "$keyword" == server ]] || continue
  endpoint="http://$node/health/ready/"
  if body="$(docker exec amaris-gateway wget -T 8 -qO- --header "Host: $address" "$endpoint")" && \
    python3 -c 'import json,sys; assert json.load(sys.stdin)["status"]=="ready"' <<< "$body"; then
    printf 'ALB node %s served Django readiness.\n' "$node"
    healthy_nodes=$((healthy_nodes + 1))
  else
    printf 'ALB node %s did not serve Django readiness.\n' "$node" >&2
  fi
done < "$nginx/amaris-alb-nodes.conf"
if [[ "$healthy_nodes" == 0 ]]; then
  echo 'No ALB node served Django readiness from the HTTPS gateway.' >&2
  exit 1
fi
systemctl disable --now amaris-private-task-gateway.timer >/dev/null
systemctl stop amaris-private-task-gateway.service >/dev/null
python3 - "$backup" "$nginx/default.conf" <<'PY'
import pathlib, sys
previous, current = map(pathlib.Path, sys.argv[1:])
content = previous.read_text()
start = content.index('    location ~ ^/(api/')
end = content.rindex('\n}')
content = content[:start] + '''    location / {
        proxy_pass http://amaris_public_alb;
        proxy_http_version 1.1;
        proxy_set_header Host 16.171.164.5;
        proxy_set_header X-Amaris-Client-IP $remote_addr;
        proxy_connect_timeout 5s;
    }''' + content[end:]
current.write_text(content.replace('X-Amaris-Network private-vpc', 'X-Amaris-Network public-alb'))
PY
docker exec amaris-gateway nginx -t >/dev/null
docker exec amaris-gateway nginx -s reload >/dev/null
for attempt in {1..12}; do
  headers="$(curl -fSs -D - -o /dev/null --max-time 8 --resolve "$address:443:127.0.0.1" "https://$address/health/ready" || true)"
  if grep -Eiq '^X-Amaris-Network: public-alb' <<< "$headers"; then break; fi
  sleep 2
done
grep -Eiq '^X-Amaris-Network: public-alb' <<< "$headers"
cat > /etc/systemd/system/amaris-alb-gateway.service <<UNIT
[Unit]
Description=Refresh Amaris staging HTTPS gateway ALB node addresses
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
ExecStart=$root/refresh-gateway.sh
UNIT
cat > /etc/systemd/system/amaris-alb-gateway.timer <<'UNIT'
[Unit]
Description=Refresh Amaris staging ALB addresses after node changes

[Timer]
OnBootSec=20sec
OnUnitActiveSec=30sec
AccuracySec=3sec

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now amaris-alb-gateway.timer >/dev/null
trap - ERR
echo 'The existing public HTTPS endpoint is serving through the ALB.'
