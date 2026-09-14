#!/bin/sh
set -eu

environment_name=${1:?environment name is required}

if [ "$environment_name" != "staging" ]; then
    echo "Backup/restore evidence drills are restricted to staging." >&2
    exit 2
fi

: "${BACKUP_WEBHOOK_URL:?BACKUP_WEBHOOK_URL is required}"
: "${BACKUP_TOKEN:?BACKUP_TOKEN is required}"

release_sha=${GITHUB_SHA:?GITHUB_SHA is required}
if ! printf '%s' "$release_sha" | grep -Eq '^[0-9a-f]{40}$'; then
    echo "GITHUB_SHA must be a full 40-character lowercase Git SHA." >&2
    exit 2
fi

evidence_file=${RESTORE_EVIDENCE_FILE:-/tmp/amaris-backup-restore-evidence.json}

post_json() {
    payload=$1
    curl \
        --fail \
        --silent \
        --show-error \
        --retry 2 \
        --retry-all-errors \
        --connect-timeout 5 \
        --max-time 1800 \
        --header "Authorization: Bearer $BACKUP_TOKEN" \
        --header "Content-Type: application/json" \
        --data "$payload" \
        "$BACKUP_WEBHOOK_URL"
}

backup_payload=$(jq -n \
    --arg environment "$environment_name" \
    --arg release_sha "$release_sha" \
    '{action: "backup", environment: $environment, release_sha: $release_sha, tag: "restore-drill"}')

backup_response=$(post_json "$backup_payload")
recovery_id=$(printf '%s' "$backup_response" | jq -er '
    select(.status == "ok" or .status == "completed" or .status == "succeeded")
    | .recovery_id
    | select(type == "string" and length > 0)
')

restore_payload=$(jq -n \
    --arg environment "$environment_name" \
    --arg release_sha "$release_sha" \
    --arg recovery_id "$recovery_id" \
    '{
        action: "restore-test",
        environment: $environment,
        release_sha: $release_sha,
        recovery_id: $recovery_id,
        target: "isolated-restore-test"
    }')

restore_response=$(post_json "$restore_payload")
printf '%s' "$restore_response" | jq -e '
    (.status == "ok" or .status == "completed" or .status == "succeeded")
    and (.integrity_verified == true)
    and (.application_smoke_verified == true)
' >/dev/null

mkdir -p "$(dirname "$evidence_file")"
jq -n \
    --arg environment "$environment_name" \
    --arg release_sha "$release_sha" \
    '{
        environment: $environment,
        release_sha: $release_sha,
        backup_status: "verified",
        restore_status: "verified",
        integrity_verified: true,
        application_smoke_verified: true
    }' >"$evidence_file"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
        echo "### Backup / restore drill"
        echo ""
        echo "- Environment: $environment_name"
        echo "- Release Git SHA: \`$release_sha\`"
        echo "- Isolated restore integrity: verified"
        echo "- Restored application smoke: verified"
        echo "- Recovery identifiers were not written to logs or artifacts."
    } >>"$GITHUB_STEP_SUMMARY"
fi
