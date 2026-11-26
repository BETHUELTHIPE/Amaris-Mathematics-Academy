#!/usr/bin/env bash
set -euo pipefail
umask 077
root=/opt/amaris-staging/shared-valkey
name=amaris-staging-shared-valkey
[[ "$private_ip" =~ ^10\.86\.0\.[0-9]+$ && "$image" =~ ^(docker\.io/)?valkey/valkey@sha256:[a-f0-9]{64}$ ]]
ip -4 addr show | grep -F " $private_ip/" >/dev/null
(( $(awk '/MemAvailable:/{print $2}' /proc/meminfo) >= 650000 ))
(( $(df -Pk /opt | awk 'NR==2{print $4}') >= 1048576 ))
install -d -m 0700 "$root" "$root/config" "$root/data" "$root/ca"
password="$(aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/host-password --with-decryption --query Parameter.Value --output text)"
[[ "$password" =~ ^[0-9a-f]{64}$ ]]
if ! docker image inspect "$image" >/dev/null 2>&1; then docker pull "$image" >/dev/null; fi
uid="$(docker run --rm --entrypoint id "$image" -u valkey)"
gid="$(docker run --rm --entrypoint id "$image" -g valkey)"
[[ "$uid" =~ ^[0-9]+$ && "$gid" =~ ^[0-9]+$ && "$uid" != 0 ]]
if [[ ! -f "$root/ca/ca.crt" ]]; then
  [[ ! -e "$root/ca/ca.key" && ! -e "$root/config/server.key" ]]
  openssl req -x509 -newkey rsa:3072 -nodes -days 365 -sha256 -subj '/CN=Amaris staging Valkey CA' \
    -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' -addext 'keyUsage=critical,keyCertSign,cRLSign' \
    -keyout "$root/ca/ca.key" -out "$root/ca/ca.crt" 2>/dev/null
  openssl req -new -newkey rsa:2048 -nodes -subj '/CN=Amaris staging Valkey' \
    -keyout "$root/config/server.key" -out "$root/ca/server.csr" 2>/dev/null
  printf 'subjectAltName=IP:%s,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n' "$private_ip" > "$root/ca/server.ext"
  openssl x509 -req -in "$root/ca/server.csr" -CA "$root/ca/ca.crt" -CAkey "$root/ca/ca.key" \
    -CAcreateserial -days 180 -sha256 -extfile "$root/ca/server.ext" -out "$root/config/server.crt" 2>/dev/null
  cp "$root/ca/ca.crt" "$root/config/ca.crt"
fi
openssl verify -CAfile "$root/ca/ca.crt" -verify_ip "$private_ip" "$root/config/server.crt" >/dev/null
openssl x509 -in "$root/config/server.crt" -checkend 604800 -noout >/dev/null
if ! docker container inspect "$name" >/dev/null 2>&1; then
  [[ -z "$(ss -ltnH 'sport = :6379')" ]]
  cat > "$root/config/valkey.conf" <<EOF
bind 127.0.0.1 $private_ip
port 0
tls-port 6379
tls-cert-file /config/server.crt
tls-key-file /config/server.key
tls-ca-cert-file /config/ca.crt
tls-auth-clients no
protected-mode yes
requirepass $password
dir /data
appendonly yes
appendfsync everysec
save 60 1
maxmemory 128mb
maxmemory-policy noeviction
EOF
  chown -R "$uid:$gid" "$root/config" "$root/data"
  chmod 0700 "$root/config" "$root/data"
  chmod 0600 "$root/config/"*
  docker run -d --name "$name" --network host --restart unless-stopped --user "$uid:$gid" \
    --memory 256m --memory-swap 256m --cpus 0.5 --log-opt max-size=5m --log-opt max-file=2 \
    --mount "type=bind,src=$root/config,dst=/config,readonly" --mount "type=bind,src=$root/data,dst=/data" \
    "$image" valkey-server /config/valkey.conf >/dev/null
fi
for attempt in {1..12}; do
  if printf '%s\n' "$password" | docker exec -i "$name" sh -ec 'read -r REDISCLI_AUTH; export REDISCLI_AUTH; valkey-cli --tls --cacert /config/ca.crt -h 127.0.0.1 ping' | grep -qx PONG; then break; fi
  sleep 2
done
printf '%s\n' "$password" | docker exec -i "$name" sh -ec 'read -r REDISCLI_AUTH; export REDISCLI_AUTH; valkey-cli --tls --cacert /config/ca.crt -h 127.0.0.1 ping' | grep -qx PONG
unset password
cat "$root/ca/ca.crt"
