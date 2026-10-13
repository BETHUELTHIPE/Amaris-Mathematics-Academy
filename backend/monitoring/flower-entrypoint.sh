#!/bin/sh
set -eu
export CELERY_BROKER_URL="$(cat /run/secrets/broker_url)"
export FLOWER_BASIC_AUTH="$(cat /run/secrets/flower_basic_auth)"
if [ -z "$CELERY_BROKER_URL" ] || [ -z "$FLOWER_BASIC_AUTH" ]; then
    echo "Flower requires broker and authentication secrets." >&2
    exit 1
fi
exec celery flower "$@"
