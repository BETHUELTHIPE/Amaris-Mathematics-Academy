#!/bin/sh
set -eu

environment_name=${1:?environment name is required}
expected_image=${2:?expected immutable image reference is required}
expected_sha=${3:?expected Git SHA is required}
health_url=${4:?health-check URL is required}
expected_tag=${expected_image##*:}

status_response=$(sh scripts/release/deploy-webhook.sh status "$environment_name")
active_image=$(printf '%s' "$status_response" | jq -er '.active.image')
active_sha=$(printf '%s' "$status_response" | jq -er '.active.git_sha')

if [ "$active_image" != "$expected_image" ] || [ "$active_sha" != "$expected_sha" ]; then
    echo "Deployment state mismatch: expected git_sha=$expected_sha image=$expected_image; received git_sha=$active_sha image=$active_image." >&2
    exit 1
fi

sh scripts/release/verify-health.sh "$health_url" "$expected_sha" "$expected_tag"
