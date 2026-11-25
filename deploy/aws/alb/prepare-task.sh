#!/usr/bin/env bash
set -euo pipefail

address="$1"
[[ "$address" == 16.171.164.5 ]]
root=/opt/amaris-staging/alb
install -d -m 0755 "$root"
if [[ ! -d "$root/valkey" ]]; then
  id="$(docker ps --filter label=com.amazonaws.ecs.task-definition-family=amaris-ecs-staging-private-web \
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

cat > "$root/backend.inc" <<NGINX
proxy_pass http://127.0.0.1:8000;
proxy_http_version 1.1;
proxy_set_header Host $address;
proxy_set_header X-Forwarded-Host $address;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For \$http_x_amaris_client_ip;
NGINX
cat > "$root/cms.conf" <<NGINX
server {
    listen 8080 default_server;
    access_log off;
    client_max_body_size 65m;
    location = /__alb/ready {
        if (\$http_user_agent !~ '^ELB-HealthChecker/') { return 404; }
        proxy_pass http://127.0.0.1:8000/health/ready/;
        proxy_set_header Host $address;
        proxy_set_header X-Forwarded-Proto https;
    }
    location ~ ^/(api/(v1|schema|docs)/|admin/|static/|health/(ready|live|version|dependencies)/) {
        include /etc/nginx/conf.d/backend.inc;
    }
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $address;
        proxy_set_header X-Forwarded-Host $address;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$http_x_amaris_client_ip;
    }
}
NGINX
chmod 644 "$root/cms.conf" "$root/backend.inc"
