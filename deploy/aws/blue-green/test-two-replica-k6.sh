#!/usr/bin/env bash
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
cluster=amaris-ecs-staging
service=amaris-web-staging-stateless
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount==2 and .runningCount==2 and .pendingCount==0 and (.deployments|length)==1 and .deployments[0].rolloutState=="COMPLETED" and (.loadBalancers|length)==1' <<< "$state" >/dev/null
rev="$(jq -er .taskDefinition <<< "$state")"
target="$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$state")"
[[ "$target" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:targetgroup/amaris-staging-stateless/* ]]
mapfile -t tasks < <(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --desired-status RUNNING --query taskArns --output json | jq -r '.[]')
[[ "${#tasks[@]}" == 2 ]]
live="$(aws ecs describe-tasks --cluster "$cluster" --tasks "${tasks[@]}" --output json)"
jq -e --arg r "$rev" '(.tasks|length)==2 and all(.tasks[];.taskDefinitionArn==$r and .lastStatus=="RUNNING" and .healthStatus=="HEALTHY") and ([.tasks[].containerInstanceArn]|unique|length)==2' <<< "$live" >/dev/null
ips="$(jq -c '[.tasks[].attachments[]|select(.type=="ElasticNetworkInterface")|.details[]|select(.name=="privateIPv4Address")|.value]|unique' <<< "$live")"
aws elbv2 describe-target-health --target-group-arn "$target" --output json | jq -e --argjson ips "$ips" '[.TargetHealthDescriptions[]|select(.TargetHealth.State=="healthy")|.Target.Id]|unique|.==$ips' >/dev/null
curl -fSs --max-time 15 https://16.171.164.5/health/ready/ | jq -e '.status=="ready"' >/dev/null
echo 'Preflight PASS: two healthy tasks on distinct EC2 hosts and both matching ALB targets.'
docker run --rm -v "$PWD/deploy/aws/blue-green:/tests:ro" grafana/k6:0.54.0 run /tests/staging-smoke.js
aws ecs describe-services --cluster "$cluster" --services "$service" --output json | jq -e '.services[0]|.runningCount==2 and .pendingCount==0 and .deployments[0].rolloutState=="COMPLETED"' >/dev/null
aws elbv2 describe-target-health --target-group-arn "$target" --output json | jq -e --argjson ips "$ips" '[.TargetHealthDescriptions[]|select(.TargetHealth.State=="healthy")|.Target.Id]|unique|.==$ips' >/dev/null
echo 'PASS: bounded 20-VU read-only k6 smoke and two healthy targets after load. Not a production capacity certification or per-target traffic distribution proof.'
