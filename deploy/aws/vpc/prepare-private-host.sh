#!/usr/bin/env bash
set -euo pipefail

address="$1"
[[ "$address" == 16.171.164.5 ]]
grep -Fxq 'ECS_CLUSTER=amaris-ecs-staging' /etc/ecs/ecs.config

install -d -m 0755 /opt/amaris-staging/vpc
root=/opt/amaris-staging/vpc
cat > "$root/cms.conf" <<NGINX
server {
    listen 127.0.0.1:8080;
    access_log off;
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $address;
        proxy_set_header X-Forwarded-Host $address;
        proxy_set_header X-Forwarded-Proto https;
    }
    location / { return 404; }
}
NGINX
chmod 644 "$root/cms.conf"
if [[ ! -d "$root/valkey" ]]; then
  id="$(docker ps --filter label=com.amazonaws.ecs.task-definition-family=amaris-ecs-staging-web \
    --filter label=com.amazonaws.ecs.container-name=valkey --format '{{.ID}}')"
  [[ "$id" =~ ^[a-f0-9]{12,64}$ ]]
  owner="$(docker exec "$id" sh -c 'printf "%s:%s" "$(id -u valkey)" "$(id -g valkey)"')"
  [[ "$owner" =~ ^[0-9]+:[0-9]+$ ]]
  volume="$(mktemp -d "$root/valkey.XXXXXX")"
  trap 'rm -rf -- "$volume"' EXIT
  docker exec "$id" valkey-cli SAVE >/dev/null
  docker cp "$id:/data/dump.rdb" "$volume/dump.rdb" >/dev/null
  chmod 640 "$volume/dump.rdb"
  chown -R "$owner" "$volume"
  chmod 750 "$volume"
  mv "$volume" "$root/valkey"
  trap - EXIT
fi

cat > "$root/nat.sh" <<'NAT'
#!/usr/bin/env bash
set -euo pipefail

interface="$(ip -4 route show default | awk 'NR==1 {print $5}')"
[[ "$interface" =~ ^[a-z0-9]+$ ]]
private=10.86.0.128/25
vpc=10.86.0.0/24
ports=443,465,587,5432,6543
sysctl -qw net.ipv4.ip_forward=1
sysctl -qw net.ipv4.conf.all.send_redirects=0
sysctl -qw "net.ipv4.conf.$interface.send_redirects=0"

iptables_once() {
  local table="$1" chain="$2"
  shift 2
  iptables -w -t "$table" -C "$chain" "$@" 2>/dev/null || iptables -w -t "$table" -I "$chain" 1 "$@"
}
iptables_once nat POSTROUTING -s "$private" ! -d "$vpc" -o "$interface" -p tcp \
  -m multiport --dports "$ports" -j MASQUERADE
iptables_once filter FORWARD -i "$interface" -o "$interface" -s "$private" ! -d "$vpc" -p tcp \
  -m multiport --dports "$ports" -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT
iptables_once filter FORWARD -i "$interface" -o "$interface" -d "$private" ! -s "$vpc" \
  -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
NAT
chmod 700 "$root/nat.sh"
cat > /etc/systemd/system/amaris-staging-private-nat.service <<UNIT
[Unit]
Description=Private IPv4 egress for the Amaris staging ECS subnets
Wants=network-online.target
Requires=docker.service
After=network-online.target docker.service
Before=ecs.service

[Service]
Type=oneshot
ExecStart=$root/nat.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable amaris-staging-private-nat.service >/dev/null
systemctl restart amaris-staging-private-nat.service

if ! grep -Fxq 'ECS_ENABLE_TASK_ENI=true' /etc/ecs/ecs.config || ! grep -Fxq 'ECS_AWSVPC_BLOCK_IMDS=true' /etc/ecs/ecs.config; then
  sed -i '/^ECS_ENABLE_TASK_ENI=/d; /^ECS_AWSVPC_BLOCK_IMDS=/d' /etc/ecs/ecs.config
  printf 'ECS_ENABLE_TASK_ENI=true\nECS_AWSVPC_BLOCK_IMDS=true\n' >> /etc/ecs/ecs.config
  systemctl restart ecs
fi
systemctl is-active --quiet ecs
printf 'Private egress rules and ENI support are configured on the staging host.\n'
