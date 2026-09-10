#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_DIR=$(dirname "$SCRIPT_DIR")
RESULTS_DIR=${LOADTEST_RESULTS_DIR:-$SCRIPT_DIR/results}
LOCUST_BIN=${LOCUST_BIN:-$BACKEND_DIR/.venv/bin/locust}
TARGET_URL=${LOADTEST_TARGET_URL:-http://127.0.0.1:8080}
PROFILE=${LOADTEST_PROFILE:-normal}

mkdir -p "$RESULTS_DIR"

LOADTEST_PROFILE="$PROFILE" "$LOCUST_BIN" \
  --locustfile "$SCRIPT_DIR/locustfile.py" \
  --host "$TARGET_URL" \
  --headless \
  --stop-timeout 15s \
  --csv "$RESULTS_DIR/$PROFILE" \
  --html "$RESULTS_DIR/$PROFILE.html"
