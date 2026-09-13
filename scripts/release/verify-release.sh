#!/bin/sh
set -eu

environment_name=${1:?environment name is required}
expected_image=${2:?expected immutable image reference is required}
expected_sha=${3:?expected Git SHA is required}
health_url=${4:?health-check URL is required}
expected_tag=${expected_image##*:}

sh scripts/release/verify-deployment-state.sh "$environment_name" "$expected_image" "$expected_sha"
sh scripts/release/verify-health.sh "$health_url" "$expected_sha" "$expected_tag"
