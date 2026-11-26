#!/usr/bin/env bash
# Render the native ECS deployment configuration with the deployed private health-probe Lambda.
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=""
stack="${BLUE_GREEN_ROUTING_STACK:-amaris-staging-blue-green-routing}"
base="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
output="${OUTPUT_PATH:-${RUNNER_TEMP:-/tmp}/amaris-bluegreen-deployment-configuration.json}"
outputs="$(aws cloudformation describe-stacks --stack-name "$stack" --query 'Stacks[0].Outputs' --output json)"
lambda_arn="$(jq -er '.[]|select(.OutputKey=="HealthProbeLambdaArn")|.OutputValue' <<< "$outputs")"
role_arn="$(jq -er '.[]|select(.OutputKey=="EcsLambdaHookRoleArn")|.OutputValue' <<< "$outputs")"
[[ "$lambda_arn" == arn:aws:lambda:eu-north-1:110156539003:function:amaris-staging-bluegreen-health-probe ]]
[[ "$role_arn" == arn:aws:iam::110156539003:role/* ]]
jq --arg lambda "$lambda_arn" --arg role "$role_arn" '
  .lifecycleHooks = ([.lifecycleHooks[]|select(.targetType != "AWS_LAMBDA")] + [
    {
      "targetType":"AWS_LAMBDA",
      "hookTargetArn":$lambda,
      "roleArn":$role,
      "lifecycleStages":["POST_TEST_TRAFFIC_SHIFT"],
      "timeoutConfiguration":{"timeoutInMinutes":5,"action":"ROLLBACK"}
    },
    {
      "targetType":"AWS_LAMBDA",
      "hookTargetArn":$lambda,
      "roleArn":$role,
      "lifecycleStages":["POST_PRODUCTION_TRAFFIC_SHIFT"],
      "timeoutConfiguration":{"timeoutInMinutes":5,"action":"ROLLBACK"}
    }
  ])
' "$base/deployment-configuration.json" > "$output"
jq -e '
  .strategy=="BLUE_GREEN" and .alarms.enable and .alarms.rollback and
  (all(.lifecycleHooks[]; .timeoutConfiguration.action=="ROLLBACK")) and
  (any(.lifecycleHooks[]; .targetType=="AWS_LAMBDA" and .lifecycleStages==["POST_TEST_TRAFFIC_SHIFT"])) and
  (any(.lifecycleHooks[]; .targetType=="AWS_LAMBDA" and .lifecycleStages==["POST_PRODUCTION_TRAFFIC_SHIFT"]))
' "$output" >/dev/null
echo "Rendered ECS blue-green deployment configuration with Lambda health hooks:"
echo "$output"
