#!/bin/sh
set -eu

umask 077

metrics_dir=${RELIABILITY_METRICS_DIR:-/var/lib/amaris-reliability}
started_at=$(date +%s)
stage_dir=$(mktemp -d)
status=0

mkdir -p "$metrics_dir"

write_attempt_metric() {
    finished_at=$(date +%s)
    metric_tmp="$metrics_dir/backup_attempt.prom.tmp.$$"
    {
        echo "# HELP amaris_backup_last_status Whether the last backup attempt succeeded."
        echo "# TYPE amaris_backup_last_status gauge"
        echo "amaris_backup_last_status $status"
        echo "# HELP amaris_backup_last_attempt_timestamp_seconds Last backup attempt time."
        echo "# TYPE amaris_backup_last_attempt_timestamp_seconds gauge"
        echo "amaris_backup_last_attempt_timestamp_seconds $finished_at"
        echo "# HELP amaris_backup_last_duration_seconds Last backup duration."
        echo "# TYPE amaris_backup_last_duration_seconds gauge"
        echo "amaris_backup_last_duration_seconds $((finished_at - started_at))"
    } > "$metric_tmp"
    mv "$metric_tmp" "$metrics_dir/backup_attempt.prom"
}

cleanup() {
    write_attempt_metric
    rm -rf "$stage_dir"
}
trap cleanup EXIT INT TERM

: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY is required}"
: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

export PGPASSWORD=$POSTGRES_PASSWORD
export RESTIC_PASSWORD_FILE

pg_dump \
    --host="${POSTGRES_HOST:-db}" \
    --port="${POSTGRES_PORT:-5432}" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --file="$stage_dir/database.dump"
pg_restore --list "$stage_dir/database.dump" >/dev/null

if [ -d /backup-source/media ]; then
    tar -C /backup-source -cf "$stage_dir/media.tar" media
fi

if ! restic snapshots >/dev/null 2>&1; then
    restic init
fi

restic backup "$stage_dir" --tag "${BACKUP_TAG:-automated}" --tag amaris
restic check --read-data-subset="${RESTIC_CHECK_SUBSET:-1/20}"
restic forget \
    --tag amaris \
    --keep-daily "${BACKUP_KEEP_DAILY:-7}" \
    --keep-weekly "${BACKUP_KEEP_WEEKLY:-5}" \
    --keep-monthly "${BACKUP_KEEP_MONTHLY:-12}" \
    --prune

status=1
success_tmp="$metrics_dir/backup_success.prom.tmp.$$"
{
    echo "# HELP amaris_backup_last_success_timestamp_seconds Last successful encrypted backup time."
    echo "# TYPE amaris_backup_last_success_timestamp_seconds gauge"
    echo "amaris_backup_last_success_timestamp_seconds $(date +%s)"
} > "$success_tmp"
mv "$success_tmp" "$metrics_dir/backup_success.prom"
touch "$metrics_dir/backup-success"
