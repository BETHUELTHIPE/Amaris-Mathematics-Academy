#!/bin/sh
set -eu

environment_name=${1:?environment name is required}

: "${BACKUP_WEBHOOK_URL:?BACKUP_WEBHOOK_URL is required for high-risk migrations}"
: "${BACKUP_TOKEN:?BACKUP_TOKEN is required for high-risk migrations}"

payload=$(jq -n \
    --arg environment "$environment_name" \
    --arg release_sha "${GITHUB_SHA:-unknown}" \
    '{action: "backup", environment: $environment, release_sha: $release_sha, tag: "pre-migration"}')

response=$(curl \
    --fail-with-body \
    --silent \
    --show-error \
    --retry 3 \
    --retry-all-errors \
    --connect-timeout 10 \
    --max-time 1800 \
    --header "Authorization: Bearer $BACKUP_TOKEN" \
    --header "Content-Type: application/json" \
    --data "$payload" \
    "$BACKUP_WEBHOOK_URL")

printf '%s' "$response" | jq -e '
    (.status == "ok" or .status == "completed" or .status == "succeeded")
    and (.recovery_id | type == "string" and length > 0)
' >/dev/null

# GitHub Actions carries this non-secret boolean to the later deployment step.
# The recovery identifier itself is deliberately not written to logs or environment output.
if [ -n "${GITHUB_ENV:-}" ]; then
    printf 'PRE_MIGRATION_BACKUP_VERIFIED=true\n' >> "$GITHUB_ENV"
fi
