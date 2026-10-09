#!/bin/sh
set -eu

action=${1:?deployment action is required}
environment_name=${2:?environment name is required}
image_reference=${3:-}

case "$action" in
    deploy|rollback)
        if ! printf '%s\n' "$image_reference" | grep -Eq '^docker[.]io/bethuelm/amaris-mathematics-academy:[0-9a-f]{40}$'; then
            echo "Deployment and rollback require an approved immutable Docker image." >&2
            exit 64
        fi
        release_sha=${image_reference##*:}
        ;;
    current-release)
        if [ -n "$image_reference" ]; then
            echo "current-release must not specify a candidate image." >&2
            exit 64
        fi
        release_sha=""
        ;;
    *) echo "Unsupported deployment action." >&2; exit 2 ;;
esac

: "${DEPLOY_WEBHOOK_URL:?DEPLOY_WEBHOOK_URL is required}"
: "${DEPLOY_TOKEN:?DEPLOY_TOKEN is required}"

payload=$(jq -n \
    --arg action "$action" \
    --arg environment "$environment_name" \
    --arg image "$image_reference" \
    --arg release_sha "$release_sha" \
    '{action: $action, environment: $environment, image: $image, release_sha: $release_sha}')

# A read-only query returns the host's active immutable image and Git SHA.
# Mutating actions are never retried blindly (no idempotency-key contract).
if [ "$action" = "current-release" ]; then
    curl \
        --fail-with-body --silent --show-error \
        --retry 2 --connect-timeout 10 --max-time 30 \
        --header "Authorization: Bearer $DEPLOY_TOKEN" \
        --header "Content-Type: application/json" \
        --data "$payload" \
        "$DEPLOY_WEBHOOK_URL"
else
    curl \
        --fail-with-body --silent --show-error \
        --retry 0 --connect-timeout 10 --max-time 120 \
        --header "Authorization: Bearer $DEPLOY_TOKEN" \
        --header "Content-Type: application/json" \
        --data "$payload" \
        "$DEPLOY_WEBHOOK_URL" >/dev/null
fi
