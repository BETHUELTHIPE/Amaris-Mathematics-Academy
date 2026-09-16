#!/usr/bin/env bash
set -euo pipefail

profile="${1:-all}"
if [[ "$profile" != "all" && "$profile" != "perfect" && "$profile" != "mobile" ]]; then
  echo "Usage: $0 [all|perfect|mobile]" >&2
  exit 2
fi

rm -rf .lighthouseci/perfect .lighthouseci/mobile
mkdir -p .lighthouseci/perfect .lighthouseci/mobile

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
  "home|http://127.0.0.1:4180/"
  "courses|http://127.0.0.1:4180/courses"
  "contact|http://127.0.0.1:4180/contact"
)

run_perfect_profile() {
  echo "Running strict Lighthouse 100% desktop profile..."
  for entry in "${urls[@]}"; do
    slug="${entry%%|*}"
    url="${entry#*|}"
    for run in 1 2 3; do
      npx --no-install lighthouse "$url" \
        --quiet \
        --preset=desktop \
        --throttling-method=provided \
        --chrome-flags="--headless --no-sandbox --disable-dev-shm-usage" \
        --output=json \
        --output=html \
        --output-path=".lighthouseci/perfect/${slug}-${run}"
    done
  done

  mapfile -t reports < <(find .lighthouseci/perfect -type f -name '*.json' | sort)
  node scripts/performance/verify-lighthouse.mjs perfect "${reports[@]}"
}

run_mobile_profile() {
  echo "Running realistic Lighthouse mobile profile..."
  for entry in "${urls[@]}"; do
    slug="${entry%%|*}"
    url="${entry#*|}"
    npx --no-install lighthouse "$url" \
      --quiet \
      --chrome-flags="--headless --no-sandbox --disable-dev-shm-usage" \
      --output=json \
      --output=html \
      --output-path=".lighthouseci/mobile/${slug}"
  done

  mapfile -t reports < <(find .lighthouseci/mobile -type f -name '*.json' | sort)
  node scripts/performance/verify-lighthouse.mjs mobile "${reports[@]}"
}

if [[ "$profile" == "all" || "$profile" == "perfect" ]]; then
  run_perfect_profile
fi
if [[ "$profile" == "all" || "$profile" == "mobile" ]]; then
  run_mobile_profile
fi
