#!/usr/bin/env bash
set -euo pipefail

export AWS_DEFAULT_REGION=eu-north-1 AWS_REGION=eu-north-1 AWS_PAGER=""
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
resource="service/$cluster/$service"
policy=amaris-staging-ecs-cpu-target
minimum=2
maximum=4
scaling=(--service-namespace ecs --scalable-dimension ecs:service:DesiredCount)

[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]] || {
  echo 'Unexpected AWS account.' >&2
  exit 1
}

report() {
  printf '%s\n' "$@" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
}

blocked() {
  report "## Staging Service Auto Scaling: blocked" "$@" "Requested task limits: $minimum–$maximum. This run made no AWS changes."
  exit 0
}

read_service() {
  aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json
}

read_target() {
  aws application-autoscaling describe-scalable-targets "${scaling[@]}" --resource-ids "$resource" \
    --query 'ScalableTargets[0]' --output json
}

read_policy() {
  aws application-autoscaling describe-scaling-policies "${scaling[@]}" --resource-id "$resource" \
    --query ScalingPolicies --output json
}

state="$(read_service)"
jq -e '.status == "ACTIVE"' <<< "$state" >/dev/null
target="$(read_target)"
policies="$(read_policy)"
report "$(jq -r '"Service counts: desired \(.desiredCount), running \(.runningCount), pending \(.pendingCount)."' <<< "$state")" \
  "$(jq -r 'if . == null then "No scalable target is registered." else
    "Current task limits: \(.MinCapacity)–\(.MaxCapacity). Scale-out paused: \(.SuspendedState.DynamicScalingOutSuspended)."
  end' <<< "$target")"

task_def="$(jq -er '.taskDefinition' <<< "$state")"
definition="$(aws ecs describe-task-definition --task-definition "$task_def" --query taskDefinition --output json)"
dependencies="$(jq -r '[
  (.containerDefinitions[]? | select(.name == "valkey") | "task-local Valkey"),
  (.volumes[]? | select((.host.sourcePath // "") != "") | "host mount: " + .name)
] | join(", ")' <<< "$definition")"
if [[ -n "$dependencies" ]]; then
  blocked "The running task definition depends on $dependencies."
fi

# A range update can raise DesiredCount even while scaling actions are suspended.
# Verify the upper limit on the active revision and ALB before applying it.
jq -e --argjson maximum "$maximum" '
  .runningCount >= $maximum and .desiredCount == .runningCount and .pendingCount == 0 and
  (.deployments | length) == 1 and (.loadBalancers | length) == 1
' <<< "$state" >/dev/null || blocked "The active ECS revision still needs a controlled test with $maximum healthy tasks behind its ALB."

port="$(jq -er '.loadBalancers[0].containerPort' <<< "$state")"
task_arns="$(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --desired-status RUNNING \
  --query 'taskArns[]' --output json | jq -r '.[]')"
mapfile -t tasks <<< "$task_arns"
(( ${#tasks[@]} >= maximum && ${#tasks[@]} <= 100 )) || blocked "ECS did not return enough running service tasks."
described="$(aws ecs describe-tasks --cluster "$cluster" --tasks "${tasks[@]}" --output json)"
ips="$(jq -c --arg task "$task_def" '
  [.tasks[] | select(.lastStatus == "RUNNING" and .taskDefinitionArn == $task) |
    .attachments[]? | select(.type == "ElasticNetworkInterface" and .status == "ATTACHED") |
    .details[] | select(.name == "privateIPv4Address") | .value] | unique
' <<< "$described")"
groups="$(jq -er '.loadBalancers[0] | [.targetGroupArn, .advancedConfiguration.alternateTargetGroupArn] | map(select(type == "string")) | unique[]' <<< "$state")"
healthy_ips="$(while IFS= read -r group; do
  aws elbv2 describe-target-health --target-group-arn "$group" --output json |
    jq -r --argjson port "$port" '.TargetHealthDescriptions[] |
      select(.TargetHealth.State == "healthy" and .Target.Port == $port) | .Target.Id'
done <<< "$groups")"
jq -en --argjson ips "$ips" --arg targets "$healthy_ips" --argjson maximum "$maximum" '
  [$targets | split("\n") | unique[] | select(. as $ip | $ips | index($ip))] | length >= $maximum
' >/dev/null || blocked "Fewer than $maximum running tasks on the active revision passed ALB health checks."

jq -e --arg policy "$policy" 'length == 1 and any(.[]; .PolicyName == $policy and .PolicyType == "TargetTrackingScaling" and
  .TargetTrackingScalingPolicyConfiguration.TargetValue == 65 and
  .TargetTrackingScalingPolicyConfiguration.PredefinedMetricSpecification.PredefinedMetricType == "ECSServiceAverageCPUUtilization")
' <<< "$policies" >/dev/null || blocked "The existing ECS CPU scaling policy needs review."
jq -e '. != null and ((.MinCapacity == 1 and .MaxCapacity == 2 and .SuspendedState.DynamicScalingOutSuspended)
  or (.MinCapacity == 2 and .MaxCapacity == 4))' <<< "$target" >/dev/null || blocked "The existing scaling target needs review."

latest="$(read_service)"
jq -e --argjson prior "$state" --argjson maximum "$maximum" '
  .taskDefinition == $prior.taskDefinition and .deployments == $prior.deployments and
  .desiredCount == .runningCount and .runningCount >= $maximum and .pendingCount == 0
' <<< "$latest" >/dev/null || blocked "The ECS service changed during validation."

# Keep the configured scheduled-scaling state and resume CPU-based scaling.
aws application-autoscaling register-scalable-target "${scaling[@]}" --resource-id "$resource" \
  --min-capacity "$minimum" --max-capacity "$maximum" \
  --suspended-state DynamicScalingInSuspended=false,DynamicScalingOutSuspended=false >/dev/null
for attempt in {1..12}; do
  if jq -e --argjson minimum "$minimum" --argjson maximum "$maximum" '
    .MinCapacity == $minimum and .MaxCapacity == $maximum and
    (.SuspendedState | (.DynamicScalingOutSuspended or .DynamicScalingInSuspended) | not)
  ' <<< "$(read_target)" >/dev/null; then
    report "ECS Service Auto Scaling is active: minimum $minimum tasks, maximum $maximum tasks, CPU target 65%."
    exit 0
  fi
  sleep 5
done
echo 'AWS did not confirm the updated scaling range.' >&2
exit 1
