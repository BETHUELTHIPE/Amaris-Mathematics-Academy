#!/usr/bin/env bash
set -euo pipefail

stage="${1:?usage: run-capacity-stage.sh <100|500|1000|2500|5000|10000|25000|50000>}"
result_dir="${CAPACITY_RESULT_DIR:-load_tests/results}"
mkdir -p "$result_dir"

export CAPACITY_USERS="$stage"
export CAPACITY_LOCUST_RESULT="$result_dir/capacity-${stage}-locust.json"
rm -f "$CAPACITY_LOCUST_RESULT"

processes="${CAPACITY_LOCUST_PROCESSES:-4}"

set +e
python -m locust \
  -f load_tests/capacity_locustfile.py \
  --headless \
  --host "$LOADTEST_TARGET_URL" \
  --processes "$processes" \
  --csv "$result_dir/locust-${stage}" \
  --csv-full-history \
  --html "$result_dir/locust-${stage}.html"
locust_status=$?
set -e

python -m load_tests.capacity_report --stage "$stage" --locust-exit-code "$locust_status"
