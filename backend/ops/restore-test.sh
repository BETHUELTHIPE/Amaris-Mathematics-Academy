#!/bin/sh
set -eu

umask 077

metrics_dir=${RELIABILITY_METRICS_DIR:-/var/lib/amaris-reliability}
restore_dir=$(mktemp -d)
started_at=$(date +%s)
status=0

mkdir -p "$metrics_dir"

cleanup() {
    finished_at=$(date +%s)
    metric_tmp="$metrics_dir/restore_test.prom.tmp.$$"
    {
        echo "# HELP amaris_restore_test_last_status Whether the last isolated restore test succeeded."
        echo "# TYPE amaris_restore_test_last_status gauge"
        echo "amaris_restore_test_last_status $status"
        echo "# HELP amaris_restore_test_last_attempt_timestamp_seconds Last restore-test attempt time."
        echo "# TYPE amaris_restore_test_last_attempt_timestamp_seconds gauge"
        echo "amaris_restore_test_last_attempt_timestamp_seconds $finished_at"
        echo "# HELP amaris_restore_test_last_duration_seconds Last restore-test duration."
        echo "# TYPE amaris_restore_test_last_duration_seconds gauge"
        echo "amaris_restore_test_last_duration_seconds $((finished_at - started_at))"
    } > "$metric_tmp"
    mv "$metric_tmp" "$metrics_dir/restore_test.prom"
    rm -rf "$restore_dir"
}
trap cleanup EXIT INT TERM

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY is required}"
: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE is required}"
: "${RESTORE_TEST_POSTGRES_HOST:?RESTORE_TEST_POSTGRES_HOST is required}"
: "${RESTORE_TEST_POSTGRES_DB:?RESTORE_TEST_POSTGRES_DB is required}"
: "${RESTORE_TEST_POSTGRES_USER:?RESTORE_TEST_POSTGRES_USER is required}"
: "${RESTORE_TEST_POSTGRES_PASSWORD:?RESTORE_TEST_POSTGRES_PASSWORD is required}"

if [ "$RESTORE_TEST_POSTGRES_HOST" = "${POSTGRES_HOST:-db}" ]; then
    echo "Refusing to run a restore test against the production database host." >&2
    exit 1
fi

export RESTIC_PASSWORD_FILE
export PGPASSWORD=$RESTORE_TEST_POSTGRES_PASSWORD

restic restore latest --tag automated --target "$restore_dir"
dump_file=$(find "$restore_dir" -type f -name database.dump -print -quit)
[ -n "$dump_file" ] || { echo "The latest backup has no database dump." >&2; exit 1; }
pg_restore --list "$dump_file" >/dev/null

dropdb --if-exists \
    --host="$RESTORE_TEST_POSTGRES_HOST" \
    --port="${RESTORE_TEST_POSTGRES_PORT:-5432}" \
    --username="$RESTORE_TEST_POSTGRES_USER" \
    "$RESTORE_TEST_POSTGRES_DB"
createdb \
    --host="$RESTORE_TEST_POSTGRES_HOST" \
    --port="${RESTORE_TEST_POSTGRES_PORT:-5432}" \
    --username="$RESTORE_TEST_POSTGRES_USER" \
    "$RESTORE_TEST_POSTGRES_DB"
pg_restore \
    --exit-on-error \
    --no-owner \
    --no-privileges \
    --host="$RESTORE_TEST_POSTGRES_HOST" \
    --port="${RESTORE_TEST_POSTGRES_PORT:-5432}" \
    --username="$RESTORE_TEST_POSTGRES_USER" \
    --dbname="$RESTORE_TEST_POSTGRES_DB" \
    "$dump_file"

psql \
    --host="$RESTORE_TEST_POSTGRES_HOST" \
    --port="${RESTORE_TEST_POSTGRES_PORT:-5432}" \
    --username="$RESTORE_TEST_POSTGRES_USER" \
    --dbname="$RESTORE_TEST_POSTGRES_DB" \
    --set=ON_ERROR_STOP=1 \
    --tuples-only \
    --command="SELECT to_regclass('public.django_migrations'), to_regclass('public.content_payment'), to_regclass('public.content_enrollment');" \
    | grep -q "django_migrations"

status=1
success_tmp="$metrics_dir/restore_test_success.prom.tmp.$$"
{
    echo "# HELP amaris_restore_test_last_success_timestamp_seconds Last successful isolated restore test time."
    echo "# TYPE amaris_restore_test_last_success_timestamp_seconds gauge"
    echo "amaris_restore_test_last_success_timestamp_seconds $(date +%s)"
} > "$success_tmp"
mv "$success_tmp" "$metrics_dir/restore_test_success.prom"
touch "$metrics_dir/restore-test-success"
