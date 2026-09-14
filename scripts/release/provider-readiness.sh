#!/usr/bin/env bash
set -euo pipefail

environment_name=${1:-staging}

: "${PROVIDER_TEST_WEBHOOK_URL:?PROVIDER_TEST_WEBHOOK_URL is required}"
: "${PROVIDER_TEST_TOKEN:?PROVIDER_TEST_TOKEN is required}"

payload=$(jq -n \
  --arg environment "$environment_name" \
  --arg release_sha "${GITHUB_SHA:-unknown}" \
  '{action:"provider_readiness", environment:$environment, release_sha:$release_sha, synthetic_only:true, allow_real_charges:false}')

response=$(curl \
  --fail-with-body \
  --silent \
  --show-error \
  --retry 3 \
  --retry-all-errors \
  --connect-timeout 10 \
  --max-time 1800 \
  --header "Authorization: Bearer $PROVIDER_TEST_TOKEN" \
  --header "Content-Type: application/json" \
  --data "$payload" \
  "$PROVIDER_TEST_WEBHOOK_URL")

printf '%s' "$response" | jq -e '
  (.status == "ok" or .status == "completed" or .status == "succeeded")
  and (.synthetic_only == true)
  and (.real_charge_created == false)
  and (.payfast_sandbox == "passed")
  and (.payment_signature_validation == "passed")
  and (.payment_idempotency == "passed")
  and (.email_delivery == "passed")
  and (.otp_verification == "passed")
  and (.password_reset == "passed")
' >/dev/null

printf '%s' "$response" | jq '{status, synthetic_only, real_charge_created, payfast_sandbox, payment_signature_validation, payment_idempotency, email_delivery, otp_verification, password_reset}'
