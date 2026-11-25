#!/usr/bin/env bash
# Read-only inspection. Does not change traffic, task definitions, or AWS resources.
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_PAGER=""
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
svc="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount>0 and .runningCount==.desiredCount and .pendingCount==0 and (.deployments|length)==1' <<< "$svc" >/dev/null
task="$(jq -er .taskDefinition <<< "$svc")"
definition="$(aws ecs describe-task-definition --task-definition "$task" --query taskDefinition --output json)"
alb="$(aws cloudformation describe-stacks --stack-name amaris-staging-alb --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerArn`].OutputValue | [0]' --output text)"
# Show only operational metadata, never environment variables or secrets.
jq '{serviceName,desiredCount,runningCount,deploymentController,deploymentConfiguration,loadBalancers,networkConfiguration}' <<< "$svc"
jq '{family,networkMode,runtimePlatform,containerDefinitions:[.containerDefinitions[]|{name,cpu,memoryReservation,memory}],volumes:[.volumes[]|{name,host}]}' <<< "$definition"
aws elbv2 describe-listeners --load-balancer-arn "$alb" --query 'Listeners[].{Port:Port,Protocol:Protocol,ListenerArn:ListenerArn,DefaultActions:DefaultActions}' --output json
group="$(jq -er '.loadBalancers[]|select(.containerName=="cms" and .containerPort==8080).targetGroupArn' <<< "$svc")"
aws elbv2 describe-target-health --target-group-arn "$group" --query 'TargetHealthDescriptions[].{Target:Target,State:TargetHealth.State}' --output json
instances="$(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output text)"
if [[ -n "$instances" && "$instances" != None ]]; then
  # shellcheck disable=SC2086
  aws ecs describe-container-instances --cluster "$cluster" --container-instances $instances --query 'containerInstances[].{status:status,agentConnected:agentConnected,remainingResources:remainingResources[?name==`CPU` || name==`MEMORY` || name==`ENI`]}' --output json
fi
if jq -e 'any(.containerDefinitions[]; .name=="valkey") or any(.volumes[]; .name=="valkey-data")' <<< "$definition" >/dev/null; then
  echo "::error::Task-local Valkey detected. Externalize persistent state and verify Celery idempotency before concurrent application revisions."
  exit 1
fi
if jq -e 'any(.volumes[]; (.host.sourcePath // "") != "")' <<< "$definition" >/dev/null; then
  echo "::error::Host bind mounts require migration or explicit multi-instance compatibility review."
  exit 1
fi
echo "Read-only preflight complete. Capacity, state compatibility, test routing, migration rollback and cost approval remain mandatory."
