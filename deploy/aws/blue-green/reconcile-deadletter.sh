#!/usr/bin/env bash
set -euo pipefail
umask 077
digest="$1"
ip="$2"
[[ "$digest" =~ ^[a-f0-9]{64}$ && "$ip" =~ ^10\.86\.0\.[0-9]+$ ]]
image="valkey/valkey@sha256:$digest"
path=/opt/amaris-staging/alb/valkey
[[ -s "$path/dump.rdb" ]]
[[ -z "$(docker ps -q --filter label=com.amazonaws.ecs.container-name=valkey)" ]]
[[ -z "$(find "$path" -maxdepth 2 -name '*.aof' -print -quit)" ]]
(( $(awk '/MemAvailable:/{print $2}' /proc/meminfo) >= 220000 ))
tmp="$(mktemp -d)"
name="amaris-deadletter-recovery-$$"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true; rm -rf "$tmp"' EXIT
cp -- "$path/dump.rdb" "$tmp/dump.rdb"
docker image inspect "$image" >/dev/null
docker run -d --name "$name" --network none --user 0:0 --memory 192m --memory-swap 192m --cpus 0.25 --log-driver none --mount "type=bind,src=$tmp,dst=/data" "$image" valkey-server --dir /data --dbfilename dump.rdb --appendonly no --save '' --bind 127.0.0.1 --protected-mode yes --maxmemory 128mb --maxmemory-policy noeviction >/dev/null
for _ in {1..20}; do if docker exec "$name" valkey-cli ping 2>/dev/null | grep -qx PONG; then break; fi; sleep 1; done
docker exec "$name" valkey-cli ping | grep -qx PONG
# Confirm the source contains only diagnostic list records, not executable queue entries.
python3 - "$name" "$tmp" <<'PY'
import json,pathlib,subprocess,sys
name,tmp=sys.argv[1:]
def cli(*args):
    return json.loads(subprocess.check_output(["docker","exec",name,"valkey-cli","--json","-n","2",*args],timeout=10))
cursor="0"; lists=set()
while True:
    cursor,keys=cli("SCAN",str(cursor))
    for k in keys:
        if cli("TYPE",k)=="list": lists.add(k)
    if str(cursor)=="0": break
assert lists=={"amaris:celery:dead-letter"}, "Unexpected source queue list"
assert cli("HLEN","unacked")==cli("ZCARD","unacked_index")==0
rows=cli("LRANGE","amaris:celery:dead-letter","0","-1")
assert len(rows)==8
for row in rows:
    d=json.loads(row)
    assert set(d)=={"task_id","task","error_type","failed_at"}, "Not diagnostic metadata"
    assert all(isinstance(v,str) for v in d.values())
pathlib.Path(tmp,"rows.json").write_text(json.dumps(rows))
print("PASS: all eight original list records are dead-letter metadata, not pending Celery messages.")
PY
# Stop the isolated copy before inspecting the live broker. Original RDB is untouched.
docker rm -f "$name" >/dev/null
backend="$(docker ps -q --filter label=com.amazonaws.ecs.task-definition-family=amaris-ecs-staging-alb-web --filter label=com.amazonaws.ecs.container-name=backend --filter health=healthy)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/host-password --with-decryption --query Parameter.Value --output json > "$tmp/pw"
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/ca --query Parameter.Value --output json > "$tmp/ca"
jq -cn --arg ip "$ip" --slurpfile password "$tmp/pw" --slurpfile ca "$tmp/ca" --slurpfile rows "$tmp/rows.json" '{ip:$ip,password:$password[0],ca:$ca[0],rows:$rows[0]}' > "$tmp/input"
code="$(cat <<'PY'
import json,sys,tempfile
from redis import Redis
from collections import Counter
v=json.load(sys.stdin)
key=b'amaris:celery:dead-letter'
source=[x.encode() for x in v['rows']]
with tempfile.NamedTemporaryFile(mode='w') as ca:
    ca.write(v['ca']);ca.flush()
    c=Redis(host=v['ip'],port=6379,db=2,password=v['password'],ssl=True,ssl_ca_certs=ca.name,ssl_cert_reqs='required',ssl_check_hostname=True,socket_connect_timeout=3,socket_timeout=5)
    assert c.hlen('unacked')==c.zcard('unacked_index')==0
    with c.pipeline() as tx:
        tx.watch(key)
        current=tx.lrange(key,0,-1)
        assert len(set(source))==len(source)
        if current==source:
            print('All eight dead-letter records already reconciled.')
        else:
            assert len(current)==7 and current==source[1:], 'Unexpected dead-letter order or content; refusing mutation'
            tx.multi()
            tx.lpush(key,source[0])
            tx.execute()
        assert c.lrange(key,0,-1)==source
    other=Counter()
    for k in c.scan_iter():
        if k!=key and c.type(k)==b'list':
            other['pending_messages']+=c.llen(k)
    print('PASS: 8/8 diagnostic records preserved, zero duplicate metadata records; no failed tasks replayed.')
    print('Normal pending queue message count: '+str(other['pending_messages']))
    print('Unacknowledged normal deliveries: 0')
PY
)"
docker exec -i "$backend" python -c "$code" < "$tmp/input"
