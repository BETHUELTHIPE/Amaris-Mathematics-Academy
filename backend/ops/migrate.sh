#!/bin/sh
set -eu

python manage.py showmigrations --plan

if [ "${MIGRATION_BACKUP_REQUIRED:-false}" = "true" ]; then
    BACKUP_TAG=pre-migration /app/ops/backup.sh
fi

python manage.py migrate --noinput
