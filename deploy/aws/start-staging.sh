#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

address="$1"
frontend="$2"
backend="$3"
region=eu-north-1
registry=110156539003.dkr.ecr.eu-north-1.amazonaws.com
certbot=certbot/certbot:v5.10.0
nginx=nginx:stable-alpine
root=/opt/amaris-staging
export AWS_PAGER=''

[[ "$address" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
for image in "$frontend" "$backend"; do
  [[ "$image" == "$registry/amaris-staging-frontend:"* ]]
done
for attempt in {1..30}; do
  docker info >/dev/null 2>&1 && break
  sleep 10
done
docker info >/dev/null 2>&1
install -d -m 700 "$root" "$root/nginx" "$root/letsencrypt"
install -d -m 755 "$root/challenges"
for service in frontend backend; do
  aws ssm get-parameter --region "$region" --name "/amaris/aws-staging/$service" \
    --with-decryption --query Parameter.Value --output json | python3 -c 'import json,sys; print(json.load(sys.stdin), end="")' \
    > "$root/$service.env.tmp"
  test -s "$root/$service.env.tmp"
  mv "$root/$service.env.tmp" "$root/$service.env"
done
aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry" >/dev/null 2>&1
docker pull "$frontend" >/dev/null
docker pull "$backend" >/dev/null
docker logout "$registry" >/dev/null
docker pull "$nginx" >/dev/null
docker pull "$certbot" >/dev/null
docker pull valkey/valkey:8-alpine >/dev/null
if ! docker network inspect amaris-staging >/dev/null 2>&1; then
  docker network create amaris-staging >/dev/null
fi
common=(--detach --restart unless-stopped --network amaris-staging --log-opt max-size=10m --log-opt max-file=2)
if ! docker container inspect amaris-redis >/dev/null 2>&1; then
  docker run "${common[@]}" --name amaris-redis valkey/valkey:8-alpine \
    valkey-server --maxmemory 128mb --maxmemory-policy noeviction >/dev/null
fi
if ! docker run --rm --network amaris-staging --env-file "$root/backend.env" -e SERVICE_ROLE=check \
  "$backend" python manage.py migrate --check --noinput > "$root/database-check.log" 2>&1; then
  echo 'The existing staging database did not pass the Django migration check.' >&2
  exit 1
fi

if ! docker run --rm -i --network amaris-staging --env-file "$root/backend.env" -e SERVICE_ROLE=check \
  "$backend" python - > "$root/storage-check.log" 2>&1 <<'PY'
import os
from urllib.request import urlopen
from uuid import uuid4

import boto3
from botocore.config import Config

client = boto3.client(
    "s3", endpoint_url=os.environ["SUPABASE_S3_ENDPOINT_URL"],
    aws_access_key_id=os.environ["SUPABASE_S3_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["SUPABASE_S3_SECRET_ACCESS_KEY"],
    region_name=os.environ["SUPABASE_S3_REGION"],
    config=Config(
        signature_version="s3v4", s3={"addressing_style": "path"}, connect_timeout=5, read_timeout=8,
        request_checksum_calculation="when_required", response_checksum_validation="when_required",
    ),
)
for setting in ("SUPABASE_S3_ADMIN_BUCKET", "SUPABASE_S3_STUDENT_BUCKET"):
    bucket = os.environ[setting]
    key = f"aws-staging-smoke/{uuid4().hex}.txt"
    body = b"Amaris AWS staging storage smoke test."
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="text/plain")
    try:
        signed_url = client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=60)
        with urlopen(signed_url, timeout=10) as response:
            if response.read(len(body) + 1) != body:
                raise RuntimeError("Staging signed download did not match the uploaded smoke object.")
    finally:
        client.delete_object(Bucket=bucket, Key=key)
PY
then
  echo 'The private staging storage smoke test failed.' >&2
  grep -Eo 'AccessDenied|NoSuchBucket|InvalidAccessKeyId|SignatureDoesNotMatch|EndpointConnectionError|AuthorizationHeaderMalformed' \
    "$root/storage-check.log" | sort -u >&2 || true
  exit 1
fi
echo 'Both private staging buckets passed an upload and signed download.'

docker rm -f amaris-frontend amaris-backend >/dev/null 2>&1 || true
docker run "${common[@]}" --name amaris-backend --env-file "$root/backend.env" "$backend" >/dev/null
docker run "${common[@]}" --name amaris-frontend --env-file "$root/frontend.env" "$frontend" >/dev/null

run_gateway() {
  docker rm -f amaris-gateway >/dev/null 2>&1 || true
  docker run "${common[@]}" --name amaris-gateway -p 80:80 -p 443:443 \
    -v "$root/nginx:/etc/nginx/conf.d:ro" \
    -v "$root/letsencrypt:/etc/letsencrypt:ro" \
    -v "$root/challenges:/var/www/acme:ro" "$nginx" >/dev/null
}

cat > "$root/nginx/default.conf" <<NGINX
server {
    listen 80 default_server;
    server_name $address;
    access_log off;
    location ^~ /.well-known/acme-challenge/ { root /var/www/acme; }
    location / { return 308 https://$address\$request_uri; }
}
NGINX
cert="$root/letsencrypt/live/amaris-staging/fullchain.pem"
if [[ ! -s "$cert" ]]; then
  run_gateway
  docker run --rm -v "$root/letsencrypt:/etc/letsencrypt" -v "$root/challenges:/var/www/acme" \
    "$certbot" certonly --non-interactive --agree-tos --register-unsafely-without-email \
    --cert-name amaris-staging --preferred-profile shortlived \
    --webroot --webroot-path /var/www/acme --ip-address "$address" > "$root/certbot.log" 2>&1 || {
      echo 'The public IP certificate request failed.' >&2
      exit 1
    }
fi

cat > "$root/nginx/backend-proxy.inc" <<NGINX
proxy_pass http://amaris-backend:8000;
proxy_http_version 1.1;
proxy_set_header Host $address;
proxy_set_header X-Forwarded-Host $address;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For \$remote_addr;
NGINX
cat >> "$root/nginx/default.conf" <<NGINX
server {
    listen 8080;
    access_log off;
    location /api/v1/ { include /etc/nginx/conf.d/backend-proxy.inc; }
    location / { return 404; }
}
server {
    listen 443 ssl default_server;
    server_name $address;
    ssl_certificate /etc/letsencrypt/live/amaris-staging/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/amaris-staging/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header X-Robots-Tag "noindex, nofollow" always;
    access_log off;
    error_log /dev/stderr warn;
    client_max_body_size 65m;
    location ~ ^/(api/(v1|schema|docs)/|admin/|static/|health/(ready|live|version|dependencies)/) {
        include /etc/nginx/conf.d/backend-proxy.inc;
    }
    location / {
        proxy_http_version 1.1;
        proxy_set_header Host $address;
        proxy_set_header X-Forwarded-Host $address;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_pass http://amaris-frontend:3000;
    }
}
NGINX
run_gateway
cat > /etc/systemd/system/amaris-staging-cert.service <<UNIT
[Unit]
Description=Renew the Amaris staging HTTPS certificate
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/docker run --rm -v $root/letsencrypt:/etc/letsencrypt -v $root/challenges:/var/www/acme $certbot renew --quiet
ExecStart=/usr/bin/docker exec amaris-gateway nginx -s reload
UNIT
cat > /etc/systemd/system/amaris-staging-cert.timer <<'UNIT'
[Unit]
Description=Renew the short-lived Amaris staging HTTPS certificate

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
RandomizedDelaySec=10m
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now amaris-staging-cert.timer >/dev/null
for attempt in {1..30}; do
  if curl --resolve "$address:443:127.0.0.1" -fSs --max-time 6 "https://$address/health/ready/" >/dev/null 2>&1; then
    echo 'Amaris staging is listening over HTTPS and its database is ready.'
    exit 0
  fi
  sleep 4
done
echo 'The staging gateway did not report backend readiness.' >&2
exit 1
