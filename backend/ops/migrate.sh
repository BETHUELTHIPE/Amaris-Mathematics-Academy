#!/bin/sh
set -eu

environment_name=${DEPLOYMENT_ENVIRONMENT:-staging}

case "$environment_name" in
    staging|production) ;;
    *) echo "DEPLOYMENT_ENVIRONMENT must be staging or production." >&2; exit 2 ;;
esac

if [ "$environment_name" = "production" ] && [ "${MIGRATION_BACKUP_REQUIRED:-false}" != "true" ]; then
    echo "Production migrations require MIGRATION_BACKUP_REQUIRED=true." >&2
    exit 2
fi

plan_file=$(mktemp)
trap 'rm -f "$plan_file"' EXIT
python manage.py migration_plan --environment "$environment_name" --json >"$plan_file"

python - "$plan_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    plan = json.load(handle)

if plan.get("status") != "succeeded":
    raise SystemExit("Migration plan did not complete successfully.")
if plan.get("destructive") is not False:
    raise SystemExit(
        "Destructive migrations are blocked. Use an expand/migrate/contract rollout."
    )
if not isinstance(plan.get("requires_backup"), bool):
    raise SystemExit("Migration plan is missing requires_backup.")
if not isinstance(plan.get("reversible"), bool):
    raise SystemExit("Migration plan is missing reversible.")
PY

cat "$plan_file"

if [ "${MIGRATION_BACKUP_REQUIRED:-false}" = "true" ]; then
    BACKUP_TAG=pre-migration /app/ops/backup.sh
fi

python manage.py migrate --noinput
