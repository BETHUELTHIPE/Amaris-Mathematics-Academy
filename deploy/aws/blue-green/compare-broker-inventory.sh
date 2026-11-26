#!/usr/bin/env bash
set -euo pipefail
umask 077
ip="$1"
mode="${2:-both}"
[[ "$ip" =~ ^10\.86\.0\.[0-9]+$ && ( "$mode" == both || "$mode" == shared-only ) ]]
family=amaris-ecs-staging-alb-web
mapfile -t containers < <(docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" --filter label=com.amazonaws.ecs.container-name=backend --filter health=healthy)
[[ "${#containers[@]}" == 1 ]]
backend="${containers[0]}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/host-password --with-decryption --query Parameter.Value --output json > "$tmp/pw"
aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/ca --query Parameter.Value --output json > "$tmp/ca"
jq -cn --arg ip "$ip" --arg mode "$mode" --slurpfile password "$tmp/pw" --slurpfile ca "$tmp/ca" '{ip:$ip,mode:$mode,password:$password[0],ca:$ca[0]}' > "$tmp/input"
code="$(cat <<'PY'
import json,sys,tempfile,hashlib,collections
from redis import Redis
v=json.load(sys.stdin)
def inspect(client):
    keys=list(client.scan_iter())
    if len(keys)>10000: raise RuntimeError('Unexpected broker size')
    msgs=collections.Counter()
    tasktypes=collections.Counter()
    for k in keys:
        if client.type(k)!=b'list': continue
        for payload in client.lrange(k,0,-1):
            # Use digest only for comparison; never print queue payloads or task IDs.
            msgs[hashlib.sha256(payload).digest()]+=1
            try:
                task=json.loads(payload).get('headers',{}).get('task','unknown')
            except Exception: task='unparseable'
            if not isinstance(task,str) or len(task)>128 or not all(c.isalnum() or c in '._-' for c in task): task='unknown'
            tasktypes[task]+=1
    return msgs,dict(tasktypes),client.hlen('unacked'),client.zcard('unacked_index')
with tempfile.NamedTemporaryFile(mode='w') as ca:
    ca.write(v['ca']);ca.flush()
    new=Redis(host=v['ip'],port=6379,db=2,password=v['password'],ssl=True,ssl_ca_certs=ca.name,ssl_cert_reqs='required',ssl_check_hostname=True,socket_connect_timeout=3,socket_timeout=5)
    n,nt,nh,nz=inspect(new)
    print('Shared broker inventory: '+json.dumps({'queued':sum(n.values()),'types':nt,'unacked':nh,'unacked_index':nz}),flush=True)
    if v['mode']=='both':
        old=Redis(host='127.0.0.1',port=6379,db=2,socket_timeout=5)
        o,ot,oh,oz=inspect(old)
        print('Source broker inventory: '+json.dumps({'queued':sum(o.values()),'types':ot,'unacked':oh,'unacked_index':oz}),flush=True)
        print('Point-in-time digest comparison: '+json.dumps({'matching':sum((o&n).values()),'source_only':sum((o-n).values()),'shared_only':sum((n-o).values())}),flush=True)
        print('No queue mutations; comparison alone does not establish job completion or safe replay.',flush=True)
PY
)"
docker exec -i "$backend" python -c "$code" < "$tmp/input"
