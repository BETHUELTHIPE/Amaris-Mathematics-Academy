#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_DIR=$(dirname "$SCRIPT_DIR")
SCENARIO=${1:-}
COMPOSE_FILE=${LOADTEST_COMPOSE_FILE:-$BACKEND_DIR/docker-compose.yml}
TARGET_URL=${LOADTEST_TARGET_URL:-http://127.0.0.1:8080}
MONITORING_SERVICES="flower prometheus grafana cadvisor postgres_exporter redis_exporter node_exporter blackbox_exporter pgadmin"

if [ "${LOADTEST_ENVIRONMENT:-}" != "staging" ] || [ "${LOADTEST_ALLOW_CHAOS:-false}" != "true" ]; then
  echo "Fault tests require LOADTEST_ENVIRONMENT=staging and LOADTEST_ALLOW_CHAOS=true." >&2
  exit 2
fi

case "$TARGET_URL" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *)
    echo "The fault runner controls the local staging Compose stack only." >&2
    exit 2
    ;;
esac

compose() {
  docker compose --env-file "$BACKEND_DIR/.env" -f "$COMPOSE_FILE" "$@"
}

recover() {
  compose start db redis celery_worker $MONITORING_SERVICES >/dev/null 2>&1 || true
}
trap recover EXIT INT TERM

run_degraded_load() {
  LOADTEST_PROFILE=degraded LOADTEST_TARGET_URL="$TARGET_URL" "$SCRIPT_DIR/run.sh"
}

case "$SCENARIO" in
  slow-database)
    compose exec -T db sh -eu -c \
      'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "BEGIN; LOCK TABLE content_course IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(45); COMMIT;"' &
    lock_pid=$!
    sleep 2
    run_degraded_load
    wait "$lock_pid"
    ;;
  redis-interruption)
    compose stop redis
    run_degraded_load
    compose start redis
    ;;
  celery-backlog)
    compose stop celery_worker
    compose exec -T web python manage.py shell -c \
      'from content.tasks import publish_scheduled_content; [publish_scheduled_content.delay() for _ in range(200)]'
    run_degraded_load
    compose start celery_worker
    ;;
  monitoring-failure)
    compose stop $MONITORING_SERVICES
    run_degraded_load
    compose start $MONITORING_SERVICES
    ;;
  *)
    echo "Usage: $0 {slow-database|redis-interruption|celery-backlog|monitoring-failure}" >&2
    exit 2
    ;;
esac

compose exec -T web curl --fail --silent http://127.0.0.1:8000/health/ready/ >/dev/null
