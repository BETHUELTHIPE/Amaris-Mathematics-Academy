#!/bin/sh
set -eu

action=${1:?deployment action is required}
environment_name=${2:?environment name is required}
image_reference=${3:-}

case "$action" in
    deploy|migrate|rollback) ;;
    *) echo "Unsupported deployment action." >&2; exit 2 ;;
esac

: "${DEPLOY_WEBHOOK_URL:?DEPLOY_WEBHOOK_URL is required}"
: "${DEPLOY_TOKEN:?DEPLOY_TOKEN is required}"

payload=$(jq -n \
    --arg action "$action" \
    --arg environment "$environment_name" \
    --arg image "$image_reference" \
    --arg release_sha "${GITHUB_SHA:-unknown}" \
    '{action: $action, environment: $environment, image: $image, release_sha: $release_sha}')

curl \
    --fail-with-body \
    --silent \
    --show-error \
    --retry 3 \
    --retry-all-errors \
    --connect-timeout 10 \
    --max-time 120 \
    --header "Authorization: Bearer $DEPLOY_TOKEN" \
    --header "Content-Type: application/json" \
    --data "$payload" \
    "$DEPLOY_WEBHOOK_URL" >/dev/null
