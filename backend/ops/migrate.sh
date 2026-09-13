#!/bin/sh
set -eu

if [ "${DEPLOYMENT_ENVIRONMENT:-}" = "production" ]; then
    exec python /app/ops/safe_migrate.py
fi

python manage.py showmigrations --plan

if [ "${MIGRATION_BACKUP_REQUIRED:-false}" = "true" ]; then
    BACKUP_TAG=pre-migration /app/ops/backup.sh
fi

python manage.py migrate --noinput
