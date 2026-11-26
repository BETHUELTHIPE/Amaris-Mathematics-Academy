#!/usr/bin/env bash
set -euo pipefail
umask 077
mode="$1"
image="$2"
path="$3"
[[ "$mode" == source || "$mode" == shared ]]
[[ "$image" =~ ^(docker\.io/)?valkey/valkey@sha256:[a-f0-9]{64}$ ]]
[[ "$path" == /opt/amaris-staging/alb/valkey ]]
tmp="$(mktemp -d)"
name="amaris-retained-broker-audit-$$"
cleanup() { if [[ "$mode" == source ]]; then docker rm -f "$name" >/dev/null 2>&1 || true; fi; rm -rf "$tmp"; }
trap cleanup EXIT
if [[ "$mode" == source ]]; then
  [[ -z "$(docker ps -q --filter label=com.amazonaws.ecs.container-name=valkey)" ]]
  if [[ ! -s "$path/dump.rdb" ]]; then
    echo '{"available":false,"reason":"no retained RDB snapshot","messages":[]}'
    exit 0
  fi
  [[ -z "$(find "$path" -maxdepth 2 -name '*.aof' -print -quit)" ]]
  (( $(awk '/MemAvailable:/{print $2}' /proc/meminfo) >= 220000 ))
  cp -- "$path/dump.rdb" "$tmp/dump.rdb"
  docker image inspect "$image" >/dev/null
  docker run -d --name "$name" --network none --user 0:0 --memory 192m --memory-swap 192m --cpus 0.25 --log-driver none --mount "type=bind,src=$tmp,dst=/data" "$image" valkey-server --dir /data --dbfilename dump.rdb --appendonly no --save '' --bind 127.0.0.1 --protected-mode yes --maxmemory 128mb --maxmemory-policy noeviction >/dev/null
  for _ in {1..20}; do if docker exec "$name" valkey-cli ping 2>/dev/null | grep -qx PONG; then break; fi; sleep 1; done
  docker exec "$name" valkey-cli ping | grep -qx PONG
else
  name=amaris-staging-shared-valkey
  aws ssm get-parameter --region eu-north-1 --name /amaris/aws-staging/shared-valkey/host-password --with-decryption --query Parameter.Value --output text > "$tmp/password"
fi
python3 - "$mode" "$name" "$tmp" <<'PY'
import hashlib,json,subprocess,sys,pathlib
mode,name,tmp=sys.argv[1:]
pw=pathlib.Path(tmp,"password").read_text() if mode=="shared" else None
def cli(*args):
    if mode=="shared":
        cmd=["docker","exec","-i",name,"sh","-ec",'read -r REDISCLI_AUTH; export REDISCLI_AUTH; exec valkey-cli --tls --cacert /config/ca.crt -h 127.0.0.1 --json -n 2 "$@"',"audit",*args]
        data=subprocess.check_output(cmd,input=pw.encode(),stderr=subprocess.DEVNULL,timeout=10)
    else:
        data=subprocess.check_output(["docker","exec",name,"valkey-cli","--json","-n","2",*args],stderr=subprocess.DEVNULL,timeout=10)
    return json.loads(data)
def digest(v): return hashlib.sha256(v.encode()).hexdigest()
messages=[];cursor="0";iterations=0
while True:
    cursor,keys=cli("SCAN",cursor)
    iterations+=1
    assert iterations<10000
    for key in keys:
        if cli("TYPE",key)!="list":continue
        for payload in cli("LRANGE",key,"0","-1"):
            try:
                head=json.loads(payload).get("headers",{})
                task=head.get("task","unknown")
                mid=head.get("id")
                assert isinstance(mid,str) and len(mid)<200
                assert isinstance(task,str) and len(task)<128 and all(c.isalnum() or c in "._-" for c in task)
            except Exception:
                mid=payload;task="unparseable"
            messages.append({"id_hash":digest(mid),"body_hash":digest(payload),"task":task})
            assert len(messages)<10000
    if str(cursor)=="0":break
print(json.dumps({"available":True,"messages":messages,"unacked":cli("HLEN","unacked"),"unacked_index":cli("ZCARD","unacked_index")}))
PY
