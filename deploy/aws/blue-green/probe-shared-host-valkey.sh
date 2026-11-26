#!/usr/bin/env bash
set -euo pipefail
umask 077
ip="$1"
[[ "$ip" =~ ^10\.86\.0\.[0-9]+$ ]]
family=amaris-ecs-staging-alb-web
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" --filter label=com.amazonaws.ecs.container-name=backend --filter health=healthy)"
worker="$(docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" --filter label=com.amazonaws.ecs.container-name=celery-worker --filter health=healthy)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ && "$worker" =~ ^[a-f0-9]{12,64}$ ]]
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/host-password --with-decryption --query Parameter.Value --output json > "$tmp/pw"
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/ca --query Parameter.Value --output json > "$tmp/ca"
jq -cn --slurpfile password "$tmp/pw" --slurpfile ca "$tmp/ca" '{password:$password[0],ca:$ca[0]}' > "$tmp/input"
py="$(cat <<'PY'
import json,sys,tempfile
from redis import Redis
from redis.exceptions import AuthenticationError
from uuid import uuid4
v=json.load(sys.stdin)
with tempfile.NamedTemporaryFile(mode='w') as ca:
    ca.write(v['ca']); ca.flush()
    config=dict(host=sys.argv[1],port=6379,ssl=True,ssl_ca_certs=ca.name,
        ssl_cert_reqs='required',ssl_check_hostname=True,socket_connect_timeout=3,socket_timeout=3)
    for db in range(4):
        c=Redis(db=db,password=v['password'],**config)
        assert c.ping()
        marker='amaris-shared-probe:'+uuid4().hex
        assert c.set(marker,'ok',ex=20,nx=True)
        try:
            assert c.get(marker)==b'ok' and 0<c.ttl(marker)<=20
        finally:
            c.delete(marker)
        print(f'Shared Valkey authenticated TLS DB {db}: PASS; existing keys={c.dbsize()}')
        c.close()
    try:
        Redis(**config).ping()
        raise AssertionError('Unauthenticated connection accepted')
    except AuthenticationError:
        print('Unauthenticated TLS commands rejected: PASS')
PY
)"
docker exec -i "$backend" python -c "$py" "$ip" < "$tmp/input"
docker exec -i "$worker" python - <<'PY'
import os,json
from pathlib import Path
from redis import Redis
for item in Path('/proc/1/environ').read_bytes().split(b'\0'):
    if item:
        key,_,value=item.decode().partition('=')
        os.environ[key]=value
from staging_celery import app
i=app.control.inspect(timeout=4)
counts={}
for method in ('active','reserved','scheduled','active_queues'):
    response=getattr(i,method)()
    assert response is not None and len(response)==1
    counts[method]=sum(len(items) for items in response.values())
b=Redis(host='127.0.0.1',port=6379,db=2,socket_timeout=3)
keys=list(b.scan_iter())
assert len(keys)<10000
counts['queued_list_items']=sum(b.llen(k) for k in keys if b.type(k)==b'list')
counts['unacked_hash']=b.hlen('unacked')
counts['unacked_index']=b.zcard('unacked_index')
counts['db_keys']={str(db):Redis(host='127.0.0.1',port=6379,db=db,socket_timeout=3).dbsize() for db in range(4)}
print('Read-only old broker inventory: '+json.dumps(counts,sort_keys=True))
print('Point-in-time inventory only; no producers were paused or queues moved.')
PY
