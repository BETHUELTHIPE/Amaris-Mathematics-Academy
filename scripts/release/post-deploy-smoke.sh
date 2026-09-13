#!/bin/sh
set -eu

: "${HEALTHCHECK_URL:?HEALTHCHECK_URL is required}"

origin_from_url() {
    printf '%s\n' "$1" | sed -E 's#^(https://[^/]+).*$#\1#'
}

require_https() {
    name=$1
    value=$2
    case "$value" in
        https://*) ;;
        *) echo "$name must use HTTPS." >&2; exit 2 ;;
    esac
}

request() {
    label=$1
    url=$2
    echo "Post-deploy smoke: $label -> $url"
    curl \
        --fail \
        --silent \
        --show-error \
        --location \
        --max-redirs 5 \
        --retry 2 \
        --retry-delay 1 \
        --max-time 20 \
        --proto '=https' \
        --tlsv1.2 \
        "$url" >/dev/null
}

default_origin=$(origin_from_url "$HEALTHCHECK_URL")
APPLICATION_URL=${APPLICATION_URL:-$default_origin}
API_BASE_URL=${API_BASE_URL:-$default_origin}
API_HEALTH_URL=${API_HEALTH_URL:-${API_BASE_URL%/}/health/ready/}

require_https "HEALTHCHECK_URL" "$HEALTHCHECK_URL"
require_https "APPLICATION_URL" "$APPLICATION_URL"
require_https "API_BASE_URL" "$API_BASE_URL"
require_https "API_HEALTH_URL" "$API_HEALTH_URL"

homepage_file=$(mktemp)
trap 'rm -f "$homepage_file"' EXIT HUP INT TERM

echo "Post-deploy smoke: homepage -> ${APPLICATION_URL%/}/"
curl \
    --fail \
    --silent \
    --show-error \
    --location \
    --max-redirs 5 \
    --retry 2 \
    --retry-delay 1 \
    --max-time 20 \
    --proto '=https' \
    --tlsv1.2 \
    "${APPLICATION_URL%/}/" >"$homepage_file"

request "health" "$HEALTHCHECK_URL"
request "login page" "${APPLICATION_URL%/}/login"
request "course catalogue" "${APPLICATION_URL%/}/courses"
request "API health" "$API_HEALTH_URL"

asset_path=$(grep -Eo '(src|href)="[^\"]*(_next/static|/static/)[^\"]*"' "$homepage_file" | head -n 1 | sed -E 's/^[^\"]*"([^\"]+)"$/\1/' || true)
if [ -z "$asset_path" ]; then
    echo "No static asset reference was found on the homepage." >&2
    exit 1
fi

case "$asset_path" in
    https://*) asset_url=$asset_path ;;
    //*) asset_url="https:$asset_path" ;;
    /*) asset_url="${APPLICATION_URL%/}$asset_path" ;;
    *) asset_url="${APPLICATION_URL%/}/$asset_path" ;;
esac

require_https "static asset URL" "$asset_url"
request "static asset" "$asset_url"

echo "Post-deploy safe smoke tests passed. No payment endpoint was called."
