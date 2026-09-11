#!/bin/sh
set -eu

action=${1:?deployment action is required}
environment_name=${2:?environment name is required}
image_reference=${3:-}

case "$action" in
    deploy|migrate|migration-plan|rollback) ;;
    *) echo "Unsupported deployment action." >&2; exit 2 ;;
esac

: "${DEPLOY_WEBHOOK_URL:?DEPLOY_WEBHOOK_URL is required}"
: "${DEPLOY_TOKEN:?DEPLOY_TOKEN is required}"

post_action() {
    action_name=$1
    payload=$(jq -n \
        --arg action "$action_name" \
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
    deploy|migrate)
        preflight_migration
        post_action "$action" >/dev/null
        ;;
    migration-plan)
        post_action migration-plan
        ;;
    rollback)
        post_action rollback >/dev/null
        ;;
esac
