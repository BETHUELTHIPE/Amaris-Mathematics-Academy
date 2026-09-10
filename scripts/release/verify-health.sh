#!/bin/sh
set -eu

health_url=${1:?health-check URL is required}
attempts=${HEALTHCHECK_ATTEMPTS:-20}
delay=${HEALTHCHECK_DELAY_SECONDS:-15}
attempt=1

while [ "$attempt" -le "$attempts" ]; do
    body=$(curl --fail --silent --show-error --connect-timeout 5 --max-time 10 "$health_url" 2>/dev/null || true)
    if printf '%s' "$body" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"(ok|ready)"'; then
        exit 0
    fi
    sleep "$delay"
    attempt=$((attempt + 1))
done

echo "Post-deployment health verification failed." >&2
exit 1
