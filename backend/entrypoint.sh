#!/bin/sh
set -eu

if [ "${SERVICE_ROLE:-web}" = "web" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
