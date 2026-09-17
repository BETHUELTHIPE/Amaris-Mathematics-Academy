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

# Lighthouse occasionally exits before producing a report because Chrome trace
# collection itself fails (for example NO_NAVSTART). Retry those process/runtime
# failures only. A successfully produced report is never retried based on its
# score; the verifier remains the authority for the unchanged 100/100 gate.
run_lighthouse_with_retry() {
  local mode="$1"
  local url="$2"
  local output_path="$3"
  local include_html="$4"
  local attempt
  local -a mode_args=()
  local -a output_args=(--output=json)

  if [[ "$mode" == "desktop" ]]; then
    mode_args+=(--preset=desktop --throttling-method=provided)
  fi
  if [[ "$include_html" == "true" ]]; then
    output_args+=(--output=html)
  fi

  for attempt in 1 2 3; do
    rm -f \
      "$output_path" \
      "${output_path}.json" \
      "${output_path}.html" \
      "${output_path}.report.json" \
      "${output_path}.report.html"

    if npx --no-install lighthouse "$url" \
      --quiet \
      "${mode_args[@]}" \
      --chrome-flags="--headless --no-sandbox --disable-dev-shm-usage" \
      "${output_args[@]}" \
      --output-path="$output_path"; then
      return 0
    fi

    if [[ "$attempt" -lt 3 ]]; then
      echo "Lighthouse runtime failed for $url ($mode), retrying process attempt $((attempt + 1))/3..." >&2
      sleep 2
    fi
  done

  echo "Lighthouse runtime failed for $url ($mode) after 3 process attempts." >&2
  return 1
}

# The production worker and Chrome both have one-time JIT/disk-cache startup work.
# Warm every audited route with ordinary requests and one disposable Lighthouse
# audit before the recorded runs. Warmups are never included in verification.
# Three raw reports per URL/profile are retained; verification requires their
# median Performance score to remain exactly 100/100 with the same metric limits.
warm_routes() {
  echo "Warming production routes before recorded Lighthouse measurements..."
  for pass in 1 2 3; do
    for entry in "${urls[@]}"; do
      url="${entry#*|}"
      curl --fail --silent --output /dev/null "$url"
    done
  done
}

warm_lighthouse_desktop() {
  echo "Warming each audited route with desktop Chrome/Lighthouse..."
  for entry in "${urls[@]}"; do
    slug="${entry%%|*}"
    url="${entry#*|}"
    output="/tmp/amaris-lighthouse-desktop-${slug}-warmup.json"
    run_lighthouse_with_retry desktop "$url" "$output" false
    rm -f "$output"
  done
}

warm_lighthouse_mobile() {
  echo "Warming each audited route with mobile Chrome/Lighthouse..."
  for entry in "${urls[@]}"; do
    slug="${entry%%|*}"
    url="${entry#*|}"
    output="/tmp/amaris-lighthouse-mobile-${slug}-warmup.json"
    run_lighthouse_with_retry mobile "$url" "$output" false
    rm -f "$output"
  done
}

run_perfect_profile() {
  echo "Running strict Lighthouse 100% desktop profile..."
  for entry in "${urls[@]}"; do
    slug="${entry%%|*}"
    url="${entry#*|}"
    for run in 1 2 3; do
      run_lighthouse_with_retry desktop "$url" ".lighthouseci/perfect/${slug}-${run}" true
    done
  done

  mapfile -t reports < <(find .lighthouseci/perfect -type f -name '*.json' | sort)
  node scripts/performance/verify-lighthouse.mjs perfect "${reports[@]}"
}

run_mobile_profile() {
  echo "Running strict Lighthouse 100% mobile profile..."
  for entry in "${urls[@]}"; do
    slug="${entry%%|*}"
    url="${entry#*|}"
    for run in 1 2 3; do
      run_lighthouse_with_retry mobile "$url" ".lighthouseci/mobile/${slug}-${run}" true
    done
  done

  mapfile -t reports < <(find .lighthouseci/mobile -type f -name '*.json' | sort)
  node scripts/performance/verify-lighthouse.mjs mobile "${reports[@]}"
}

warm_routes
if [[ "$profile" == "all" || "$profile" == "perfect" ]]; then
  warm_lighthouse_desktop
  run_perfect_profile
fi
if [[ "$profile" == "all" || "$profile" == "mobile" ]]; then
  warm_lighthouse_mobile
  run_mobile_profile
fi
