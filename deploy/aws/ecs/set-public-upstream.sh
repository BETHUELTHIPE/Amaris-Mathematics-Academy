#!/usr/bin/env bash
set -euo pipefail

address="$1"
mode="$2"
[[ "$address" == 16.171.164.5 ]]
root=/opt/amaris-staging
conf="$root/nginx/default.conf"
proxy="$root/nginx/backend-proxy.inc"
backup="$root/ecs/legacy-nginx"

restore() {
  if [[ ! -s "$backup/default.conf" || ! -s "$backup/backend-proxy.inc" ]]; then
    echo 'No legacy proxy backup is available.' >&2
    return 1
  fi
  docker start amaris-redis amaris-backend amaris-frontend >/dev/null
  docker update --restart unless-stopped amaris-redis amaris-backend amaris-frontend >/dev/null
  cp "$backup/default.conf" "$conf"
  cp "$backup/backend-proxy.inc" "$proxy"
  docker exec amaris-gateway nginx -t >/dev/null
  docker exec amaris-gateway nginx -s reload >/dev/null
}

case "$mode" in
  rollback)
    restore
    echo 'The public staging gateway was restored to the previous containers.'
    exit 0
    ;;
  retire-legacy)
    grep -Fq 'add_header X-Amaris-Compute ecs always;' "$conf"
    docker update --restart no amaris-frontend amaris-backend amaris-redis >/dev/null
    docker stop --time 20 amaris-frontend amaris-backend amaris-redis >/dev/null
    echo 'The previous application containers are stopped and available for rollback.'
    exit 0
    ;;
  switch) ;;
  *) exit 2 ;;
esac

bridge="$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')"
[[ "$bridge" =~ ^172\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
frontend="http://$bridge:13000"
backend="http://$bridge:18000"
docker exec amaris-gateway wget -qO- "$frontend/health/ready" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'
docker exec amaris-gateway wget -qO- --header "Host: $address" --header 'X-Forwarded-Proto: https' \
  "$backend/health/ready/" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ready"'

if grep -Fq 'add_header X-Amaris-Compute ecs always;' "$conf"; then
  echo 'The public staging gateway is already using ECS.'
  exit 0
fi

grep -Fq 'proxy_pass http://amaris-frontend:3000;' "$conf"
grep -Fq 'proxy_pass http://amaris-backend:8000;' "$proxy"
install -d -m 0700 "$backup"
cp "$conf" "$backup/default.conf"
cp "$proxy" "$backup/backend-proxy.inc"
trap 'restore || true' ERR
sed -e "s|proxy_pass http://amaris-frontend:3000;|proxy_pass $frontend;|" \
    -e '/add_header X-Robots-Tag/a\    add_header X-Amaris-Compute ecs always;' "$backup/default.conf" > "$conf"
sed "s|proxy_pass http://amaris-backend:8000;|proxy_pass $backend;|" "$backup/backend-proxy.inc" > "$proxy"
docker exec amaris-gateway nginx -t >/dev/null
docker exec amaris-gateway nginx -s reload >/dev/null
curl -fSs --retry 3 --max-time 8 --resolve "$address:443:127.0.0.1" "https://$address/health/ready/" >/dev/null
authenticated_header="$(curl -fSsI --retry 3 --max-time 8 --resolve "$address:443:127.0.0.1" "https://$address/health/ready")"
grep -Eiq '^X-Amaris-Compute: ecs' <<< "$authenticated_header"
trap - ERR
echo 'The staging HTTPS gateway now routes to the ECS task.'
