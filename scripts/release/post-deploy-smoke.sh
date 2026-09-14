#!/usr/bin/env bash
set -euo pipefail

base_url=${1:?base URL is required}
api_base_url=${SMOKE_API_BASE_URL:-$base_url}

trimmed_base=${base_url%/}
trimmed_api=${api_base_url%/}

case "$trimmed_base" in
  https://*) ;;
  http://127.0.0.1:*|http://localhost:*) ;;
  *) echo "Smoke testing requires HTTPS outside localhost." >&2; exit 2 ;;
esac

curl_check() {
  url=$1
  curl --fail-with-body --silent --show-error \
    --retry 3 --retry-all-errors \
    --connect-timeout 10 --max-time 30 \
    "$url" >/dev/null
}

curl_check "$trimmed_base/"
curl_check "$trimmed_base/login"
curl_check "$trimmed_base/courses"
curl_check "$trimmed_api/health/"
curl_check "$trimmed_api/health/ready/"

homepage=$(curl --fail --silent --show-error --connect-timeout 10 --max-time 30 "$trimmed_base/")
asset=$(printf '%s' "$homepage" | grep -oE '/_next/static/[^"'"'"' <]+' | head -n 1 || true)
if [[ -z "$asset" ]]; then
  echo "No Next.js static asset reference was found on the homepage." >&2
  exit 1
fi
curl_check "$trimmed_base$asset"

echo "Post-deployment smoke checks passed for $trimmed_base"
