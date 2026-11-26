#!/usr/bin/env bash
set -euo pipefail
umask 077
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
cluster=amaris-ecs-staging
root=deploy/aws/blue-green
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
aws ecs describe-services --cluster "$cluster" --services amaris-web-staging-alb amaris-staging-singleton-jobs --output json | jq -e '(.services|length)==2 and all(.services[];.desiredCount==0 and .runningCount==0 and .pendingCount==0)' >/dev/null
legacy="$(aws ecs describe-task-definition --task-definition amaris-ecs-staging-alb-web:3 --query taskDefinition --output json)"
image="$(jq -er '.containerDefinitions[]|select(.name=="valkey")|.image' <<< "$legacy")"
[[ "$image" =~ ^(docker\.io/)?valkey/valkey@sha256:[a-f0-9]{64}$ ]]
digest="${image##*:}"
path="$(jq -er '.volumes[]|select(.name=="valkey-data")|.host.sourcePath' <<< "$legacy")"
[[ "$path" == /opt/amaris-staging/alb/valkey ]]
first="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost --query StackResourceDetail.PhysicalResourceId --output text)"
second="$(aws cloudformation describe-stack-resource --stack-name amaris-staging-ecs-second-host --logical-resource-id SecondHost --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$first" =~ ^i-[a-f0-9]+$ && "$second" =~ ^i-[a-f0-9]+$ && "$first" != "$second" ]]
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "Inspecting original retained broker snapshot."
bash deploy/aws/ecs/run-on-host.sh "$first" "$root/inventory-retained-broker.sh" source "$digest" "$path" > "$tmp/source1.json"
echo "Inspecting second host retained broker snapshot."
bash deploy/aws/ecs/run-on-host.sh "$second" "$root/inventory-retained-broker.sh" source "$digest" "$path" > "$tmp/source2.json"
echo "Inspecting shared broker."
bash deploy/aws/ecs/run-on-host.sh "$second" "$root/inventory-retained-broker.sh" shared "$digest" "$path" > "$tmp/shared.json"
python3 - "$tmp" <<'PY'
import collections,json,pathlib,sys
p=pathlib.Path(sys.argv[1])
data=[json.loads((p/f).read_text()) for f in ("source1.json","source2.json","shared.json")]
for name,d in zip(("Original host retained snapshot","Second host retained snapshot","Shared broker"),data):
    print(name+": "+json.dumps({"available":d["available"],"queue_count":len(d["messages"]),"task_types":dict(collections.Counter(m["task"] for m in d["messages"])),"unacked":d.get("unacked"),"unacked_index":d.get("unacked_index"),"message_shapes":d.get("shapes",[])}))
shared=collections.Counter(m["id_hash"] for m in data[2]["messages"])
for name,d in zip(("Original host","Second host"),data[:2]):
    if not d["available"]:continue
    src=collections.Counter(m["id_hash"] for m in d["messages"])
    a={m["id_hash"]:m["body_hash"] for m in d["messages"]}
    b={m["id_hash"]:m["body_hash"] for m in data[2]["messages"]}
    print(name+" vs shared: "+json.dumps({"matching_ids":sum((src&shared).values()),"source_only":sum((src-shared).values()),"shared_only":sum((shared-src).values()),"changed_payloads":sum(a[k]!=b[k] for k in a.keys()&b.keys()),"duplicate_ids_source":sum(n-1 for n in src.values() if n>1),"duplicate_ids_shared":sum(n-1 for n in shared.values() if n>1)}))
print("Retained RDBs were read from isolated copies. No job replay, broker mutation or worker activation; database-side delivery evidence still required.")
PY
