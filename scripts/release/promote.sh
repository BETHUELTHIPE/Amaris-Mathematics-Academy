#!/bin/sh
set -eu

environment_name=${1:?environment name is required}
candidate_image=${2:?immutable image reference is required}

: "${HEALTHCHECK_URL:?HEALTHCHECK_URL is required}"

record_file=${DEPLOYMENT_RECORD_FILE:-deployment-version.json}
image_prefix="docker.io/bethuelm/amaris-mathematics-academy:"

extract_sha() {
    image=$1
    case "$image" in
        "${image_prefix}"*) ;;
        *) echo "Image must use the approved Amaris Docker Hub repository." >&2; exit 2 ;;
    esac
    sha=${image#"$image_prefix"}
    if ! printf '%s' "$sha" | grep -Eq '^[0-9a-f]{40}$'; then
        echo "Image tag must be a full 40-character lowercase Git SHA; latest is not an accepted deployment identity." >&2
        exit 2
    fi
    printf '%s' "$sha"
}

write_record() {
    status=$1
    active_image=$2
    active_sha=$3
    rollback_health=$4
    jq -n \
        --arg environment "$environment_name" \
        --arg status "$status" \
        --arg previous_image "$previous_image" \
        --arg previous_sha "$previous_sha" \
        --arg candidate_image "$candidate_image" \
        --arg candidate_sha "$candidate_sha" \
        --arg active_image "$active_image" \
        --arg active_sha "$active_sha" \
        --arg rollback_health "$rollback_health" \
        '{environment: $environment, status: $status, previous: {image: $previous_image, git_sha: $previous_sha}, candidate: {image: $candidate_image, git_sha: $candidate_sha}, active: {image: $active_image, git_sha: $active_sha}, rollback_health: $rollback_health}' \
        >"$record_file"
}

append_summary() {
    status=$1
    active_image=$2
    active_sha=$3
    rollback_health=$4
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
        {
            echo "### Deployment version record"
            echo ""
            echo "- Environment: $environment_name"
            echo "- Previous Git SHA: \`$previous_sha\`"
            echo "- Previous Docker image: \`$previous_image\`"
            echo "- Candidate Git SHA: \`$candidate_sha\`"
            echo "- Candidate Docker image: \`$candidate_image\`"
            echo "- Final status: $status"
            echo "- Active Git SHA: \`$active_sha\`"
            echo "- Active Docker image: \`$active_image\`"
            echo "- Rollback health: $rollback_health"
        } >>"$GITHUB_STEP_SUMMARY"
    fi
}

candidate_sha=$(extract_sha "$candidate_image")
current_release=$(scripts/release/deploy-webhook.sh current-release "$environment_name")
previous_image=$(printf '%s' "$current_release" | jq -er '.image')
previous_sha=$(printf '%s' "$current_release" | jq -er '.release_sha')
validated_previous_sha=$(extract_sha "$previous_image")
if [ "$validated_previous_sha" != "$previous_sha" ]; then
    echo "Current release image tag does not match its recorded Git SHA." >&2
    exit 2
fi

printf 'Deploying candidate Git SHA %s with image %s; rollback target is Git SHA %s with image %s.\n' \
    "$candidate_sha" "$candidate_image" "$previous_sha" "$previous_image"
write_record "deploying" "$previous_image" "$previous_sha" "not-required"

scripts/release/deploy-webhook.sh deploy "$environment_name" "$candidate_image"

release_ok=false
if scripts/release/verify-health.sh "$HEALTHCHECK_URL"; then
    if [ "$environment_name" = "production" ]; then
        if scripts/release/post-deploy-smoke.sh; then
            release_ok=true
        else
            echo "Production post-deploy smoke checks failed." >&2
        fi
    else
        release_ok=true
    fi
fi

if [ "$release_ok" = "true" ]; then
    write_record "succeeded" "$candidate_image" "$candidate_sha" "not-required"
    append_summary "succeeded" "$candidate_image" "$candidate_sha" "not-required"
    exit 0
fi

echo "The new release failed critical health or post-deploy checks; rolling back to the exact previously active immutable image." >&2
scripts/release/deploy-webhook.sh rollback "$environment_name" "$previous_image"

if scripts/release/verify-health.sh "$HEALTHCHECK_URL"; then
    write_record "rolled-back" "$previous_image" "$previous_sha" "passed"
    append_summary "rolled-back" "$previous_image" "$previous_sha" "passed"
    echo "Rollback restored the previous release and health checks passed." >&2
    exit 1
fi

write_record "rollback-failed" "$previous_image" "$previous_sha" "failed"
append_summary "rollback-failed" "$previous_image" "$previous_sha" "failed"
echo "Rollback was requested but the restored release failed health checks." >&2
exit 2
