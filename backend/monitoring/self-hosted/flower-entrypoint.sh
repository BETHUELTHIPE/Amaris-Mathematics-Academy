#!/bin/sh
set -eu
CELERY_BROKER_URL=$(cat /run/secrets/broker_url)
export CELERY_BROKER_URL
exec celery --broker="$CELERY_BROKER_URL" flower "$@"
