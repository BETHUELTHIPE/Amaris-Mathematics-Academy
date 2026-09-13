#!/bin/sh
set -eu

health_url=${1:?health-check URL is required}
expected_sha=${2:?expected Git SHA is required}
expected_image_tag=${3:?expected Docker image tag is required}
attempts=${HEALTHCHECK_ATTEMPTS:-20}
delay=${HEALTHCHECK_DELAY_SECONDS:-15}
attempt=1

while [ "$attempt" -le "$attempts" ]; do
    body=$(curl --fail --silent --show-error --connect-timeout 5 --max-time 10 "$health_url" 2>/dev/null || true)
    if printf '%s' "$body" | jq -e \
        --arg sha "$expected_sha" \
        --arg image_tag "$expected_image_tag" \
        '(.status == "ok" or .status == "ready")
         and .version.git_sha == $sha
         and .version.image_tag == $image_tag' >/dev/null 2>&1; then
        return_code=0
        break
    fi
    return_code=1
    if [ "$attempt" -lt "$attempts" ]; then
        sleep "$delay"
    fi
    attempt=$((attempt + 1))
done

if [ "$return_code" -eq 0 ]; then
    echo "Health check passed for git_sha=$expected_sha image_tag=$expected_image_tag."
    exit 0
fi

echo "Health check failed for git_sha=$expected_sha image_tag=$expected_image_tag." >&2
exit 1
