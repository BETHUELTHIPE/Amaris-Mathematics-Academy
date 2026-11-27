#!/usr/bin/env bash
set -euo pipefail
cluster=amaris-ecs-staging
service=amaris-web-staging-stateless
tasks="$(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --desired-status RUNNING --query taskArns --output json)"
mapfile -t arns < <(jq -r '.[]' <<< "$tasks")
[[ "${#arns[@]}" == 2 ]]
nodes=()
ids=()
for arn in "${arns[@]}"; do
  task="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$arn" --query 'tasks[0]' --output json)"
  jq -e '.healthStatus=="HEALTHY" and .lastStatus=="RUNNING" and .group=="service:amaris-web-staging-stateless"' <<< "$task" >/dev/null
  instance="$(aws ecs describe-container-instances --cluster "$cluster" --container-instances "$(jq -r .containerInstanceArn <<< "$task")" --query 'containerInstances[0].ec2InstanceId' --output text)"
  nodes+=("$instance")
  ids+=("${arn##*/}")
done
nonce="$(python -c 'import uuid;print(uuid.uuid4().hex)')"
probe() {
  bash deploy/aws/ecs/run-on-host.sh "${nodes[$1]}" deploy/aws/diagnostics/supabase-retention.sh "${ids[$1]}" "$2" "$nonce"
}
cleanup() {
  code=$?
  trap - EXIT
  if ! probe 0 clean && ! probe 1 clean; then exit 1; fi
  exit "$code"
}
trap cleanup EXIT
probe 0 write
probe 1 verify
echo 'The second running ECS replica read the files created by the first.'
