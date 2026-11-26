#!/usr/bin/env bash
set -euo pipefail
task="$1"
[[ "$task" =~ ^[a-f0-9]{32}$ ]]
arn="arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$task"
worker="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$arn" --filter label=com.amazonaws.ecs.container-name=celery-worker --filter health=healthy)"
beat="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$arn" --filter label=com.amazonaws.ecs.container-name=celery-beat --filter health=healthy)"
[[ "$worker" =~ ^[a-f0-9]{12,64}$ && "$beat" =~ ^[a-f0-9]{12,64}$ ]]
docker exec -i "$worker" python - <<'PY'
import os,sys
from pathlib import Path
for item in Path('/proc/1/environ').read_bytes().split(b'\0'):
    if item:
        k,_,v=item.decode().partition('=')
        os.environ[k]=v
sys.path.insert(0,'/tmp')
from staging_celery import app
from urllib.parse import urlsplit
assert urlsplit(app.conf.broker_url).scheme=='rediss'
assert urlsplit(app.conf.result_backend).scheme=='rediss'
reply=app.control.inspect(timeout=5).active_queues()
assert reply and len(reply)==1
assert {q['name'] for q in next(iter(reply.values()))}=={'default','critical','notifications'}
for q in ('default','critical','notifications'):
    result=app.send_task('amaris.staging.celery_probe',queue=q,expires=40)
    try:
        assert result.get(timeout=25)=={'status':'ok','queue':q}
        print('PASS shared broker worker round trip: '+q,flush=True)
    finally:
        result.forget()
print('One worker and one healthy Beat container verified.',flush=True)
PY
