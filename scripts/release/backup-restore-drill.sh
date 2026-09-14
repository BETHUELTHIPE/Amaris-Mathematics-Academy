#!/usr/bin/env bash
set -euo pipefail

environment_name=${1:-staging}

: "${RESTORE_TEST_WEBHOOK_URL:?RESTORE_TEST_WEBHOOK_URL is required}"
: "${RESTORE_TEST_TOKEN:?RESTORE_TEST_TOKEN is required}"

payload=$(jq -n \
  --arg environment "$environment_name" \
  --arg release_sha "${GITHUB_SHA:-unknown}" \
  '{action:"backup_restore_drill", environment:$environment, release_sha:$release_sha}')

response=$(curl \
  --fail-with-body \
  --silent \
  --show-error \
  --retry 3 \
  --retry-all-errors \
  --connect-timeout 10 \
  --max-time 3600 \
  --header "Authorization: Bearer $RESTORE_TEST_TOKEN" \
  --header "Content-Type: application/json" \
  --data "$payload" \
  "$RESTORE_TEST_WEBHOOK_URL")

printf '%s' "$response" | jq -e '
  (.status == "ok" or .status == "completed" or .status == "succeeded")
  and (.backup_id | type == "string" and length > 0)
  and (.restore_id | type == "string" and length > 0)
  and (.integrity_check == "passed")
  and (.application_smoke_check == "passed")
' >/dev/null

printf '%s' "$response" | jq '{status, backup_id, restore_id, integrity_check, application_smoke_check, rpo_seconds, rto_seconds}'
