#!/usr/bin/env bash
set -euo pipefail

environment_name=${1:?environment name is required}
previous_image=${2:?previous immutable image is required}
candidate_image=${3:?candidate immutable image is required}

: "${HEALTHCHECK_URL:?HEALTHCHECK_URL is required}"

for image in "$previous_image" "$candidate_image"; do
  if [[ -z "$image" || "$image" == *":latest" ]]; then
    echo "Rollback drill requires immutable image references, not :latest." >&2
    exit 2
  fi
done

if [[ "$previous_image" == "$candidate_image" ]]; then
  echo "Rollback drill requires distinct previous and candidate images." >&2
  exit 2
fi

echo "Rolling back $environment_name to previous image."
scripts/release/deploy-webhook.sh rollback "$environment_name" "$previous_image"
scripts/release/verify-health.sh "$HEALTHCHECK_URL"

echo "Restoring candidate image after rollback verification."
scripts/release/deploy-webhook.sh deploy "$environment_name" "$candidate_image"
scripts/release/verify-health.sh "$HEALTHCHECK_URL"

echo "Rollback drill passed and candidate was restored."
