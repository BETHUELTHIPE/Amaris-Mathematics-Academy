#!/bin/sh
set -eu

stop=0
trap 'stop=1' INT TERM

while [ "$stop" -eq 0 ]; do
    /app/ops/backup.sh || true
    remaining=${BACKUP_INTERVAL_SECONDS:-21600}
    while [ "$remaining" -gt 0 ] && [ "$stop" -eq 0 ]; do
        step=60
        [ "$remaining" -lt "$step" ] && step=$remaining
        sleep "$step" &
        wait $! || true
        remaining=$((remaining - step))
    done
done
