#!/bin/sh
set -eu

environment_name=${1:?environment name is required}
image_reference=${2:?immutable candidate image reference is required}

: "${HEALTHCHECK_URL:?HEALTHCHECK_URL is required}"

image_pattern='^docker[.]io/bethuelm/amaris-mathematics-academy:[0-9a-f]{40}$'
require_immutable_image() {
    printf '%s\n' "$1" | grep -Eq "$image_pattern"
}

if ! require_immutable_image "$image_reference"; then
    echo "Candidate must be the approved Docker Hub image tagged with a full immutable Git SHA." >&2
    exit 64
fi

candidate_sha=${image_reference##*:}
if [ -n "${GITHUB_SHA:-}" ] && [ "$candidate_sha" != "$GITHUB_SHA" ]; then
    echo "Candidate Docker image tag does not match the release Git SHA." >&2
    exit 64
fi

# Current-release MUST be read from the deployment host, not inferred from
# GitHub, the previous workflow, or an ambiguous latest tag.
if ! previous_release=$(scripts/release/deploy-webhook.sh current-release "$environment_name"); then
    echo "Cannot establish the currently active release; deployment refused." >&2
    exit 65
fi

previous_image=$(printf '%s' "$previous_release" | jq -er '
    select(.status == "ok" and (.image | type == "string") and (.git_sha | type == "string"))
    | .image
') || {
    echo "Current-release response is missing authenticated version evidence." >&2
    exit 65
}
previous_sha=${previous_image##*:}
if ! require_immutable_image "$previous_image" || ! printf '%s' "$previous_release" | jq -e --arg sha "$previous_sha" '.git_sha == $sha' >/dev/null; then
    echo "Existing release is not an immutable, Git-SHA-matched image; deployment refused." >&2
    exit 65
fi

verify_active_image() {
    expected_image=$1
    expected_sha=${expected_image##*:}
    active_release=$(scripts/release/deploy-webhook.sh current-release "$environment_name") || return 1
    printf '%s' "$active_release" | jq -e \
        --arg expected_image "$expected_image" \
        --arg expected_sha "$expected_sha" \
        '.status == "ok" and .image == $expected_image and .git_sha == $expected_sha' >/dev/null
}

if [ "$previous_image" = "$image_reference" ]; then
    # An idempotent promotion is acceptable only if that version is healthy.
    scripts/release/verify-health.sh "$HEALTHCHECK_URL"
    verify_active_image "$image_reference"
    exit 0
fi

echo "Deploying immutable candidate ${candidate_sha}; previous image SHA is ${previous_sha}."
scripts/release/deploy-webhook.sh deploy "$environment_name" "$image_reference"

if scripts/release/verify-health.sh "$HEALTHCHECK_URL" && verify_active_image "$image_reference"; then
    echo "Candidate ${candidate_sha} is active and healthy."
    exit 0
fi

echo "Candidate unhealthy or wrong version; rolling back to recorded immutable image ${previous_sha}." >&2
if ! scripts/release/deploy-webhook.sh rollback "$environment_name" "$previous_image"; then
    echo "CRITICAL: rollback command failed; intervention required." >&2
    exit 71
fi
if ! scripts/release/verify-health.sh "$HEALTHCHECK_URL"; then
    echo "CRITICAL: previous image did not recover to healthy status." >&2
    exit 72
fi
if ! verify_active_image "$previous_image"; then
    echo "CRITICAL: rollback health passed but active version does not match the recorded previous image." >&2
    exit 73
fi
echo "Rollback verified: previous immutable image ${previous_sha} is active and healthy." >&2
# Promotion itself must remain failed even when recovery succeeds.
exit 1
