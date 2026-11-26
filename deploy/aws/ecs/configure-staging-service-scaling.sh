#!/usr/bin/env bash
set -euo pipefail

export AWS_DEFAULT_REGION=eu-north-1 AWS_REGION=eu-north-1 AWS_PAGER=""
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
policy=amaris-staging-ecs-cpu-target
resource="service/$cluster/$service"
scaling=(--service-namespace ecs --scalable-dimension ecs:service:DesiredCount)

[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]] || {
  echo 'Unexpected AWS account.' >&2
  exit 1
}

read_service() {
  aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json
}

service_state="$(read_service)"
jq -e '.status == "ACTIVE" and .desiredCount == 1 and .runningCount == 1 and .pendingCount == 0
  and (.deployments | length) == 1' <<< "$service_state" >/dev/null || {
  echo 'Expected the staging service to be stable at one running task.' >&2
  exit 1
}
task_def="$(jq -er .taskDefinition <<< "$service_state")"
task="$(aws ecs describe-task-definition --task-definition "$task_def" --query taskDefinition --output json)"
blockers="$(jq -r '[
  (.containerDefinitions[]? | select(.name == "valkey") | "task-local Valkey"),
  (.volumes[]? | select((.host.sourcePath // "") != "") | "host mount: " + .name)
] | join(", ")' <<< "$task")"
if [[ -n "$blockers" ]]; then
  echo "Staging scale-out will stay paused while the running task uses $blockers."
else
  echo 'Staging scale-out will stay paused until a second task passes load-balancer health checks in a controlled test.'
fi

echo 'Checking the previous EC2 Auto Scaling stack outcome.'
if ! aws cloudformation describe-stack-events --stack-name amaris-staging-ecs-autoscaling \
  --query 'StackEvents[0:12].[LogicalResourceId,ResourceStatus,ResourceStatusReason]' --output table; then
  echo '::warning::The EC2 Auto Scaling stack events could not be read.'
fi

read_target() {
  aws application-autoscaling describe-scalable-targets "${scaling[@]}" --resource-ids "$resource" \
    --query 'ScalableTargets[0]' --output json
}

read_policies() {
  aws application-autoscaling describe-scaling-policies "${scaling[@]}" --resource-id "$resource" \
    --query ScalingPolicies --output json
}

existing="$(read_target)"
if [[ "$existing" != null ]]; then
  jq -e '.MinCapacity == 1 and .MaxCapacity == 2 and .SuspendedState.DynamicScalingOutSuspended' \
    <<< "$existing" >/dev/null || { echo 'An existing scaling target needs review before any update.' >&2; exit 1; }
  jq -e --arg policy "$policy" 'all(.[]; .PolicyName == $policy)' <<< "$(read_policies)" >/dev/null || {
    echo 'An existing scaling policy needs review before any update.' >&2
    exit 1
  }
fi

# Keep the active one-task service stable while its host-local state is migrated.
suspended='DynamicScalingInSuspended=true,DynamicScalingOutSuspended=true,ScheduledScalingSuspended=true'
aws application-autoscaling register-scalable-target "${scaling[@]}" --resource-id "$resource" \
  --min-capacity 1 --max-capacity 2 --suspended-state "$suspended" >/dev/null

target='{"TargetValue":65,"PredefinedMetricSpecification":{"PredefinedMetricType":"ECSServiceAverageCPUUtilization"},"ScaleOutCooldown":120,"ScaleInCooldown":300}'
for attempt in {1..12}; do
  if [[ "$(read_target)" != null ]]; then
    break
  fi
  sleep 5
done
aws application-autoscaling put-scaling-policy "${scaling[@]}" --resource-id "$resource" \
  --policy-name "$policy" --policy-type TargetTrackingScaling --target-tracking-scaling-policy-configuration "$target" >/dev/null

jq -e '.MinCapacity == 1 and .MaxCapacity == 2 and
  (.SuspendedState | .DynamicScalingInSuspended and .DynamicScalingOutSuspended and .ScheduledScalingSuspended)' \
  <<< "$(read_target)" >/dev/null
for attempt in {1..12}; do
  if jq -e --arg policy "$policy" --argjson target "$target" 'any(.[]; .PolicyName == $policy and
    .PolicyType == "TargetTrackingScaling" and (.TargetTrackingScalingPolicyConfiguration | del(.DisableScaleIn)) == $target)' \
    <<< "$(read_policies)" >/dev/null; then
    break
  fi
  [[ "$attempt" -lt 12 ]] || { echo 'AWS did not return the expected scaling policy.' >&2; exit 1; }
  sleep 5
done
jq -e --arg task "$task_def" '.taskDefinition == $task and .desiredCount == 1 and .runningCount == 1' \
  <<< "$(read_service)" >/dev/null

{
  echo 'ECS Service Auto Scaling target and CPU policy verified in Stockholm.'
  echo 'Task limits: 1–2. CPU target: 65%. Scaling activity: paused. Running tasks: 1.'
  if [[ -n "$blockers" ]]; then
    echo "The active task still uses $blockers."
  fi
} | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
