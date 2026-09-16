#!/usr/bin/env bash
set -euo pipefail

mkdir -p .lighthouseci

bash scripts/performance/start-lighthouse-server.sh > /tmp/amaris-lighthouse-server.log 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT

for attempt in {1..45}; do
  if curl --fail --silent http://127.0.0.1:4180/ >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 45 ]; then
    cat /tmp/amaris-lighthouse-server.log
    exit 1
  fi
  sleep 2
done

urls=(
  "http://127.0.0.1:4180/"
  "http://127.0.0.1:4180/courses"
  "http://127.0.0.1:4180/contact"
)

index=0
for url in "${urls[@]}"; do
  index=$((index + 1))
  npx --no-install lighthouse "$url" \
    --quiet \
    --chrome-flags="--headless --no-sandbox --disable-dev-shm-usage" \
    --output=json \
    --output-path=".lighthouseci/run-${index}.json"
done

node scripts/performance/verify-lighthouse.mjs .lighthouseci/run-1.json .lighthouseci/run-2.json .lighthouseci/run-3.json
