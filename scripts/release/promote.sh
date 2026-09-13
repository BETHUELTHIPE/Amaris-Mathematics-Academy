#!/bin/sh
set -eu

environment_name=${1:?environment name is required}
image_reference=${2:?immutable image reference is required}
release_sha=${GITHUB_SHA:?GITHUB_SHA is required}
record_path=${DEPLOYMENT_RECORD_PATH:-deployment-record.json}
image_tag=${image_reference##*:}
force_rollback_test=${FORCE_ROLLBACK_TEST:-false}

: "${HEALTHCHECK_URL:?HEALTHCHECK_URL is required}"

validate_release() {
    candidate_image=$1
    candidate_sha=$2
    candidate_tag=${candidate_image##*:}

    printf '%s' "$candidate_sha" | grep -Eq '^[0-9a-f]{40}$' || {
        echo "Release Git SHA must be a full 40-character lowercase hexadecimal SHA." >&2
        return 1
    }
    [ "$candidate_tag" != "latest" ] || {
        echo "The mutable latest tag cannot be deployed." >&2
        return 1
    }
    [ "$candidate_tag" = "$candidate_sha" ] || {
        echo "Docker image tag must exactly match the release Git SHA." >&2
        return 1
    }
}

write_record() {
    outcome=$1
    restored_image=${2:-}
    restored_sha=${3:-}
    jq -n \
        --arg environment "$environment_name" \
        --arg outcome "$outcome" \
        --arg candidate_image "$image_reference" \
        --arg candidate_git_sha "$release_sha" \
        --arg previous_image "$previous_image" \
        --arg previous_git_sha "$previous_sha" \
        --arg restored_image "$restored_image" \
        --arg restored_git_sha "$restored_sha" \
        --arg recorded_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{environment: $environment, outcome: $outcome,
          candidate: {image: $candidate_image, git_sha: $candidate_git_sha},
          previous: {image: $previous_image, git_sha: $previous_git_sha},
          restored: (if $restored_image == "" then null else {image: $restored_image, git_sha: $restored_git_sha} end),
          recorded_at: $recorded_at}' > "$record_path"
}

validate_release "$image_reference" "$release_sha"

previous_status=$(sh scripts/release/deploy-webhook.sh status "$environment_name")
previous_image=$(printf '%s' "$previous_status" | jq -er '.active.image')
previous_sha=$(printf '%s' "$previous_status" | jq -er '.active.git_sha')
validate_release "$previous_image" "$previous_sha"

if [ "$previous_image" = "$image_reference" ]; then
    echo "The requested image is already active; no release was performed." >&2
    write_record already_active
    exit 0
fi

echo "Deploying git_sha=$release_sha image=$image_reference to $environment_name."
sh scripts/release/deploy-webhook.sh deploy "$environment_name" "$image_reference" "$release_sha" >/dev/null

if [ "$force_rollback_test" != "true" ] && \
    sh scripts/release/verify-release.sh "$environment_name" "$image_reference" "$release_sha" "$HEALTHCHECK_URL"; then
    write_record deployed
    exit 0
fi

if [ "$force_rollback_test" = "true" ]; then
    echo "Rollback drill: deliberately treating the candidate as unhealthy." >&2
else
    echo "The candidate release is unhealthy." >&2
fi
echo "Rolling back to git_sha=$previous_sha image=$previous_image." >&2
if ! sh scripts/release/deploy-webhook.sh rollback "$environment_name" "$previous_image" "$previous_sha" >/dev/null; then
    write_record rollback_request_failed
    echo "CRITICAL: the rollback request failed." >&2
    exit 2
fi

if sh scripts/release/verify-release.sh "$environment_name" "$previous_image" "$previous_sha" "$HEALTHCHECK_URL"; then
    if [ "$force_rollback_test" = "true" ]; then
        write_record rollback_test_passed "$previous_image" "$previous_sha"
        echo "Rollback drill passed: git_sha=$previous_sha image=$previous_image is healthy." >&2
        exit 0
    fi
    write_record rolled_back "$previous_image" "$previous_sha"
    echo "Rollback verified: git_sha=$previous_sha image=$previous_image is healthy." >&2
    exit 1
fi

write_record rollback_verification_failed
echo "CRITICAL: rollback completed without restoring the previously healthy release." >&2
exit 2
