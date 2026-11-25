#!/usr/bin/env bash
# Read-only: never update ECS, modify ALB routing or force alarm states.
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=""
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config="$dir/deployment-configuration.json"
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
topic=arn:aws:sns:eu-north-1:110156539003:amaris-staging-cloudwatch-alarms
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
jq -e '.strategy=="BLUE_GREEN" and .alarms.enable and .alarms.rollback and .minimumHealthyPercent==100 and .maximumPercent==200 and .bakeTimeInMinutes>=15 and (.alarms.alarmNames|sort)==["amaris-staging-alb-5xx","amaris-staging-slow-responses","amaris-staging-target-5xx"]' "$config" >/dev/null
mapfile -t names < <(jq -r '.alarms.alarmNames[]' "$config")
stack_names="$(aws cloudformation describe-stacks --stack-name amaris-staging-monitoring --query 'Stacks[0].Outputs[?OutputKey==`DeploymentRollbackAlarmNames`].OutputValue | [0]' --output text)"
jq -e --arg actual "$stack_names" '.alarms.alarmNames|sort==($actual|split(",")|sort)' "$config" >/dev/null
svc="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount>0' <<< "$svc" >/dev/null
definition="$(aws ecs describe-task-definition --task-definition "$(jq -er .taskDefinition <<< "$svc")" --query taskDefinition --output json)"
alb="$(aws cloudformation describe-stacks --stack-name amaris-staging-alb --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerArn`].OutputValue | [0]' --output text)"
[[ "$alb" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:loadbalancer/app/* ]]
alb_name="${alb#*loadbalancer/}"
alarms="$(aws cloudwatch describe-alarms --alarm-names "${names[@]}" --output json)"
jq -e --arg topic "$topic" --arg alb "$alb_name" --slurpfile cfg "$config" '
  ([.MetricAlarms[].AlarmName]|sort)==($cfg[0].alarms.alarmNames|sort) and
  all(.MetricAlarms[]; .ActionsEnabled and .Namespace=="AWS/ApplicationELB" and
    (.Dimensions==[{"Name":"LoadBalancer","Value":$alb}]) and
    (.AlarmActions|index($topic))!=null and (.OKActions|index($topic))!=null and
    .TreatMissingData=="notBreaching" and
    ((.AlarmName=="amaris-staging-alb-5xx" and .MetricName=="HTTPCode_ELB_5XX_Count" and .Threshold==5 and .Statistic=="Sum") or
     (.AlarmName=="amaris-staging-target-5xx" and .MetricName=="HTTPCode_Target_5XX_Count" and .Threshold==5 and .Statistic=="Sum") or
     (.AlarmName=="amaris-staging-slow-responses" and .MetricName=="TargetResponseTime" and .Threshold==2 and .ExtendedStatistic=="p95")))
' <<< "$alarms" >/dev/null
jq '[.MetricAlarms[]|{AlarmName,StateValue,MetricName,Threshold}]' <<< "$alarms"
echo "Verified monitoring stack exports and rollback alarm definitions."
jq '{serviceName,desiredCount,runningCount,pendingCount,controller:.deploymentController.type,strategy:(.deploymentConfiguration.strategy // "ROLLING"),currentRollbackAlarms:.deploymentConfiguration.alarms,advancedRouting:([.loadBalancers[]?|select(.advancedConfiguration != null)]|length)}' <<< "$svc"
jq '{architecture:.runtimePlatform.cpuArchitecture,localValkey:any(.containerDefinitions[]; .name=="valkey"),hostMountCount:([.volumes[]?|select((.host.sourcePath//"")!="")]|length),requestedCpu:([.containerDefinitions[]|.cpu//0]|add),requestedMemoryMiB:([.containerDefinitions[]|.memoryReservation//.memory//0]|add)}' <<< "$definition"
instances="$(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output text)"
if [[ -n "$instances" && "$instances" != None ]]; then
  read -r -a arns <<< "$instances"
  aws ecs describe-container-instances --cluster "$cluster" --container-instances "${arns[@]}" --query 'containerInstances[].{status:status,agentConnected:agentConnected,remainingResources:remainingResources[?name==`CPU` || name==`MEMORY` || name==`ENI`]}' --output json | jq '[.[]|{status,agentConnected,resources:[.remainingResources[]|{name,integerValue}]}]'
fi
# Fail closed: ECS may ignore pre-existing ALARM states for an entire deployment.
blocked=0
if ! jq -e 'all(.MetricAlarms[]; .StateValue=="OK")' <<< "$alarms" >/dev/null; then
  echo "::error::Rollback alarms must all be OK before starting any deployment."
  blocked=1
fi
if ! jq -e '.runningCount==.desiredCount and .pendingCount==0 and (.deployments|length)==1 and .deploymentController.type=="ECS" and .deploymentConfiguration.strategy=="BLUE_GREEN" and any(.loadBalancers[]?; .advancedConfiguration.alternateTargetGroupArn != null and .advancedConfiguration.productionListenerRule != null and .advancedConfiguration.testListenerRule != null and .advancedConfiguration.roleArn != null)' <<< "$svc" >/dev/null; then
  echo "::error::Service is not a stable native blue-green service with production and test routing."
  blocked=1
fi
if jq -e 'any(.containerDefinitions[]; .name=="valkey") or any(.volumes[]?; (.host.sourcePath//"")!="")' <<< "$definition" >/dev/null; then
  echo "::error::Task-local state or host bind mounts block safe concurrent revisions."
  blocked=1
fi
if (( blocked )); then
  echo "Alarm definitions verified; live activation blocked by release prerequisites."
  exit 1
fi
echo "Alarm preflight passed. Capacity, database compatibility and rollback acceptance still require independent verification."
