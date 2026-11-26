#!/usr/bin/env bash
set -euo pipefail

family=amaris-ecs-staging-alb-web
for attempt in {1..20}; do
  worker="$(docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" --filter label=com.amazonaws.ecs.container-name=celery-worker --filter health=healthy)"
  beat="$(docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" --filter label=com.amazonaws.ecs.container-name=celery-beat --filter health=healthy)"
  if [[ "$worker" =~ ^[a-f0-9]{12,64}$ && "$beat" =~ ^[a-f0-9]{12,64}$ ]]; then break; fi
  sleep 4
done
if [[ ! "$worker" =~ ^[a-f0-9]{12,64}$ || ! "$beat" =~ ^[a-f0-9]{12,64}$ ]]; then
  docker ps -a --filter "label=com.amazonaws.ecs.task-definition-family=$family" --format '{{.Names}} {{.Status}}' >&2
  echo 'Exactly one healthy Celery worker and Beat are required.' >&2
  exit 1
fi
for attempt in {1..12}; do
  if docker exec -i "$worker" python - <<'PY'
import os
import sys

for line in os.environ['AMARIS_RUNTIME_ENV'].splitlines():
    key, _, value = line.partition('=')
    os.environ[key] = value
os.environ.update(CELERY_BROKER_URL='redis://127.0.0.1:6379/2', CELERY_RESULT_BACKEND='redis://127.0.0.1:6379/3')
try:
    from staging_celery import app
    required = {'notifications', 'critical', 'default'}
    workers = app.control.inspect(timeout=3).active_queues() or {}
    assert len(workers) == 1
    assert {entry['name'] for entry in next(iter(workers.values()))} == required
except Exception as error:
    print('Worker readiness check:', type(error).__name__, file=sys.stderr)
    sys.exit(1)
PY
  then break; fi
  sleep 3
done
docker exec -i "$worker" python - <<'PY'
import os
import sys

for line in os.environ['AMARIS_RUNTIME_ENV'].splitlines():
    key, _, value = line.partition('=')
    os.environ[key] = value
os.environ.update(CELERY_BROKER_URL='redis://127.0.0.1:6379/2', CELERY_RESULT_BACKEND='redis://127.0.0.1:6379/3')
try:
    from staging_celery import app
    queues = ('notifications', 'critical', 'default')
    workers = app.control.inspect(timeout=3).active_queues() or {}
    assert len(workers) == 1 and {row['name'] for row in next(iter(workers.values()))} == set(queues)
    for queue in queues:
        result = app.send_task('amaris.staging.celery_probe', queue=queue, expires=25)
        try:
            assert result.get(timeout=20) == {'status': 'ok', 'queue': queue}
        finally:
            result.forget()
        print(f'Synthetic broker and worker round trip passed for {queue}.', flush=True)
except Exception as error:
    print('Celery round-trip check failed:', type(error).__name__, file=sys.stderr)
    sys.exit(1)
PY
for attempt in {1..16}; do
  scheduler_log="$(docker logs --tail 250 "$beat" 2>&1)"
  worker_log="$(docker logs --tail 350 "$worker" 2>&1)"
  if grep -Fq 'Sending due task deliver-live-class-confirmation' <<< "$scheduler_log" &&
    grep -Fq 'Sending due task deliver-live-class-reminder' <<< "$scheduler_log" &&
    grep -Eq 'Task content\.tasks\.deliver_live_class_confirmation\[.*\] succeeded' <<< "$worker_log" &&
    grep -Eq 'Task content\.tasks\.deliver_live_class_reminder\[.*\] succeeded' <<< "$worker_log"; then
    echo 'Beat published the real booking confirmation and reminder jobs, and the worker completed both.'
    exit 0
  fi
  sleep 5
done
echo 'The scheduled booking jobs did not both complete during verification.' >&2
exit 1
