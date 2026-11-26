#!/usr/bin/env bash
set -euo pipefail
umask 077
conf=/opt/amaris-staging/nginx/default.conf
backup=/opt/amaris-staging/alb/shared-valkey-cutover-gateway.conf
mode="$1"
[[ "$mode" == on || "$mode" == off ]]
exec 9>/run/amaris-shared-valkey-gateway.lock
flock -x 9
if [[ "$mode" == on ]]; then
  [[ ! -e "$backup" ]]
  grep -Fq 'X-Amaris-Network public-alb' "$conf"
  cp -p "$conf" "$backup"
  if ! python3 - "$conf" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1])
s=p.read_text()
needle='        proxy_pass http://amaris_public_alb;'
assert s.count(needle)==1
p.write_text(s.replace(needle,'        return 503; # amaris shared broker cutover\n'+needle))
PY
  then cp "$backup" "$conf"; rm -f "$backup"; exit 1; fi
else
  [[ -s "$backup" ]]
  cp "$backup" "$conf"
fi
if ! docker exec amaris-gateway nginx -t >/dev/null || ! docker exec amaris-gateway nginx -s reload >/dev/null; then
  cp "$backup" "$conf"
  docker exec amaris-gateway nginx -t && docker exec amaris-gateway nginx -s reload
  exit 1
fi
if [[ "$mode" == on ]]; then
  for _ in {1..10}; do
    code="$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' --resolve 16.171.164.5:443:127.0.0.1 https://16.171.164.5/ || true)"
    [[ "$code" == 503 ]] && break
    sleep 1
  done
  [[ "$code" == 503 ]]
  echo 'Public staging gateway entered maintenance.'
else
  rm -f "$backup"
  echo 'Public staging gateway restored.'
fi
