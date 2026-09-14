#!/usr/bin/env bash
set -euo pipefail

base_url=${1:?base URL is required}
protected_path=${2:-/dashboard}
trimmed=${base_url%/}

case "$trimmed" in
  https://*) ;;
  http://127.0.0.1:*|http://localhost:*) ;;
  *) echo "Security-header verification requires HTTPS outside localhost." >&2; exit 2 ;;
esac

headers=$(mktemp)
protected_headers=$(mktemp)
trap 'rm -f "$headers" "$protected_headers"' EXIT

curl --fail --silent --show-error --head --connect-timeout 10 --max-time 30 "$trimmed/" > "$headers"
curl --silent --show-error --head --connect-timeout 10 --max-time 30 "$trimmed$protected_path" > "$protected_headers"

require_header() {
  name=$1
  if ! grep -Eiq "^${name}:" "$headers"; then
    echo "Missing required security header: $name" >&2
    exit 1
  fi
}

require_header 'Content-Security-Policy'
require_header 'X-Content-Type-Options'
require_header 'Referrer-Policy'
require_header 'Permissions-Policy'

if [[ "$trimmed" == https://* ]]; then
  require_header 'Strict-Transport-Security'
fi

if ! grep -Eiq '^Cache-Control:.*(private|no-store)' "$protected_headers"; then
  echo "Protected route $protected_path is not explicitly private/no-store." >&2
  exit 1
fi

echo "TLS/header/cache verification passed for $trimmed"
