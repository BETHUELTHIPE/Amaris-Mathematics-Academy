#!/usr/bin/env bash
set -euo pipefail
umask 077
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
jobs=amaris-staging-singleton-jobs
root=deploy/aws/blue-green
runner=deploy/aws/ecs/run-on-host.sh
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
python3 "$root/inspect-cutover-state.py"
state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
first="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost --query StackResourceDetail.PhysicalResourceId --output text)"
second="$(aws cloudformation describe-stack-resource --stack-name amaris-staging-ecs-second-host --logical-resource-id SecondHost --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$first" =~ ^i-[a-f0-9]+$ && "$second" =~ ^i-[a-f0-9]+$ ]]
ip="$(aws ec2 describe-instances --instance-ids "$second" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)"
taskdef="$(aws ecs describe-task-definition --task-definition "$(jq -er .taskDefinition <<< "$state")" --query taskDefinition --output json)"
if jq -e 'any(.containerDefinitions[];.name=="valkey")' <<< "$taskdef" >/dev/null; then
  echo 'Legacy service restored: source broker still authoritative until reconciliation.'
  # Read only queue counts on both brokers, never publish, consume, flush or copy.
  bash "$runner" "$first" "$root/compare-broker-inventory.sh" "$ip"
  target="$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$state")"
  aws elbv2 describe-target-health --target-group-arn "$target" --output json | jq -e '[.TargetHealthDescriptions[]|select(.TargetHealth.State=="healthy")]|length==1' >/dev/null
  curl -fSs --max-time 15 https://16.171.164.5/health/ready/ | jq -e '.status=="ready"' >/dev/null
  echo 'Legacy staging website is healthy; no duplicate destination jobs replayed.'
else
  echo 'Stateless revision remains active. Inspect shared broker from its live backend without modifying data.'
  mapfile -t tasks < <(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --desired-status RUNNING --query taskArns --output json | jq -r '.[]')
  for task in "${tasks[@]}"; do
    detail="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query 'tasks[0]' --output json)"
    if ! jq -e '.lastStatus=="RUNNING" and any(.containers[];.name=="backend" and .healthStatus=="HEALTHY")' <<< "$detail" >/dev/null; then continue; fi
    host="$(aws ecs describe-container-instances --cluster "$cluster" --container-instances "$(jq -er .containerInstanceArn <<< "$detail")" --query 'containerInstances[0].ec2InstanceId' --output text)"
    bash "$runner" "$host" "$root/compare-broker-inventory.sh" "$ip" shared-only
    break
  done
  echo 'Do not re-enable workers or overwrite broker until source and shared queue identities are reconciled.'
fi
