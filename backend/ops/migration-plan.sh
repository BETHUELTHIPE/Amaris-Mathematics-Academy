#!/bin/sh
set -eu

environment_name=${DEPLOYMENT_ENVIRONMENT:-staging}

case "$environment_name" in
    staging|production) ;;
    *) echo "DEPLOYMENT_ENVIRONMENT must be staging or production." >&2; exit 2 ;;
esac

# Read-only: this command inspects Django's migration graph and the target database's
# applied-migration state. It does not call migrate and must not modify schema/data.
exec python manage.py migration_plan --environment "$environment_name" --json
