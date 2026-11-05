#!/bin/sh
set -eu

environment_name=${1:?environment name is required}
image_reference=${2:?immutable image reference is required}

: "${HEALTHCHECK_URL:?HEALTHCHECK_URL is required}"

scripts/release/deploy-webhook.sh deploy "$environment_name" "$image_reference"

if scripts/release/verify-health.sh "$HEALTHCHECK_URL"; then
    exit 0
fi

echo "The new release is unhealthy; requesting rollback." >&2
scripts/release/deploy-webhook.sh rollback "$environment_name" "$image_reference"
scripts/release/verify-health.sh "$HEALTHCHECK_URL" || true
exit 1
