#!/usr/bin/env bash
set -euo pipefail
umask 077
ip="$1"
[[ "$ip" =~ ^10\.86\.0\.[0-9]+$ ]]
family=amaris-ecs-staging-alb-web
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" --filter label=com.amazonaws.ecs.container-name=backend --filter health=healthy)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/host-password --with-decryption --query Parameter.Value --output json > "$tmp/pw"
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/ca --query Parameter.Value --output json > "$tmp/ca"
jq -cn --arg ip "$ip" --slurpfile password "$tmp/pw" --slurpfile ca "$tmp/ca" '{ip:$ip,password:$password[0],ca:$ca[0]}' > "$tmp/input"
code="$(cat <<'PY'
import json,sys,tempfile,collections
from redis import Redis
from uuid import uuid4
v=json.load(sys.stdin)
with tempfile.NamedTemporaryFile(mode='w') as ca:
    ca.write(v['ca']); ca.flush()
    kwargs=dict(host=v['ip'],port=6379,password=v['password'],ssl=True,ssl_ca_certs=ca.name,ssl_cert_reqs='required',ssl_check_hostname=True,socket_connect_timeout=3,socket_timeout=5)
    for db in range(4):
        old=Redis(host='127.0.0.1',port=6379,db=db,socket_timeout=3)
        new=Redis(db=db,**kwargs)
        assert new.dbsize()==0, 'Destination not empty: reconcile before retry'
        kinds=collections.Counter(old.type(k).decode('ascii') for k in old.scan_iter())
        assert set(kinds)<= {'none','string','list','hash','set','zset'}
        print(f'Old DB {db} key types: {dict(kinds)}; destination empty',flush=True)
        key='amaris-migration-probe:'+uuid4().hex
        try:
            with new.pipeline(transaction=True) as tx:
                tx.rpush(key,b'first',b'second')
                tx.pexpire(key,30000)
                tx.execute()
            assert new.lrange(key,0,-1)==[b'first',b'second']
            assert new.pttl(key)>0
        finally: new.delete(key)
        print(f'DB {db} ordered list copy and TTL check passed',flush=True)
    old=Redis(host='127.0.0.1',port=6379,db=2,socket_timeout=3)
    assert not old.hlen('unacked') and not old.zcard('unacked_index')
    print('Source unacknowledged-job guard passed; no source mutations performed.',flush=True)
PY
)"
docker exec -i "$backend" python -c "$code" < "$tmp/input"
