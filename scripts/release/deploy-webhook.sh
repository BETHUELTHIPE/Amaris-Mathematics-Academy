#!/bin/sh
set -eu

action=${1:?deployment action is required}
environment_name=${2:?environment name is required}
image_reference=${3:-}

case "$action" in
    current-release|rollback-target|deploy|migrate|migration-plan|rollback) ;;
    *) echo "Unsupported deployment action." >&2; exit 2 ;;
esac

: "${DEPLOY_WEBHOOK_URL:?DEPLOY_WEBHOOK_URL is required}"
: "${DEPLOY_TOKEN:?DEPLOY_TOKEN is required}"

image_prefix="docker.io/bethuelm/amaris-mathematics-academy:"
release_sha=""

validate_immutable_image() {
    case "$image_reference" in
        "${image_prefix}"*) ;;
        *) echo "Image must use the approved immutable Amaris Docker Hub repository." >&2; exit 2 ;;
    esac

    release_sha=${image_reference#"$image_prefix"}
    if ! printf '%s' "$release_sha" | grep -Eq '^[0-9a-f]{40}$'; then
        echo "Image tag must be a full 40-character lowercase Git SHA; ambiguous tags such as latest are forbidden." >&2
        exit 2
    fi
}

post_action() {
    action_name=$1
    if [ -n "$image_reference" ]; then
        payload=$(jq -n \
            --arg action "$action_name" \
            --arg environment "$environment_name" \
            --arg image "$image_reference" \
            --arg release_sha "$release_sha" \
            '{action: $action, environment: $environment, image: $image, release_sha: $release_sha}')
    else
        payload=$(jq -n \
            --arg action "$action_name" \
            --arg environment "$environment_name" \
            '{action: $action, environment: $environment}')
    fi

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
        "$DEPLOY_WEBHOOK_URL"
}

preflight_migration() {
    # Repository-level fail-closed scan: known destructive operations are never auto-approved.
    python3 scripts/release/check_migration_safety.py \
        --root backend \
        --json-output /tmp/amaris-migration-static-report.json >/dev/null

    # Environment-aware plan: the deployment service must inspect the candidate image
    # against the target database without applying the migration.
    plan_file=/tmp/amaris-migration-plan.json
    post_action migration-plan >"$plan_file"
    python3 scripts/release/verify_migration_plan.py "$environment_name" --file "$plan_file"
}

case "$action" in
    current-release|rollback-target)
        post_action "$action"
        ;;
    deploy|migrate)
        validate_immutable_image
        preflight_migration
        post_action "$action" >/dev/null
        ;;
    migration-plan)
        validate_immutable_image
        post_action migration-plan
        ;;
    rollback)
        validate_immutable_image
        post_action rollback >/dev/null
        ;;
esac
