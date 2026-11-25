#!/usr/bin/env bash
set -euo pipefail

address="$1"
[[ "$address" == 16.171.164.5 ]]
root=/opt/amaris-staging/ecs
install -d -m 0755 "$root"
cat > "$root/cms.conf" <<NGINX
server {
    listen 8080;
    access_log off;
    location /api/v1/ {
        proxy_pass http://amaris-backend:8000;
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
  owner="$(docker exec amaris-redis sh -c 'printf "%s:%s" "$(id -u valkey)" "$(id -g valkey)"')"
  [[ "$owner" =~ ^[0-9]+:[0-9]+$ ]]
  volume="$(mktemp -d "$root/valkey.XXXXXX")"
  trap 'rm -rf -- "$volume"' EXIT
  docker exec amaris-redis valkey-cli SAVE >/dev/null
  docker cp amaris-redis:/data/dump.rdb "$volume/dump.rdb" >/dev/null
  chmod 640 "$volume/dump.rdb"
  chown -R "$owner" "$volume"
  chmod 750 "$volume"
  mv "$volume" "$root/valkey"
  trap - EXIT
fi
nginx="$(docker image inspect --format '{{index .RepoDigests 0}}' nginx:stable-alpine)"
valkey="$(docker image inspect --format '{{index .RepoDigests 0}}' valkey/valkey:8-alpine)"
printf '%s\n%s\n' "$nginx" "$valkey"
