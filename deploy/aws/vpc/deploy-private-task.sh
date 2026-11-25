#!/usr/bin/env bash
set -euo pipefail

validate_id() { [[ "$1" =~ ^"$2"-[a-f0-9]+$ ]]; }
validate_id "$STAGING_PRIVATE_PRIMARY" subnet
validate_id "$STAGING_PRIVATE_SECONDARY" subnet
validate_id "$STAGING_PRIVATE_SG" sg
legacy="$(aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$LEGACY_SERVICE" \
  --query 'services[0].taskDefinition' --output text)"
[[ "$legacy" == arn:aws:ecs:eu-north-1:110156539003:task-definition/amaris-ecs-staging-web:* ]]
definition="$(aws ecs describe-task-definition --task-definition "$legacy" --query taskDefinition --output json)"
role="$(jq -er .executionRoleArn <<< "$definition")"
nginx="$(jq -er '.containerDefinitions[]|select(.name=="cms").image' <<< "$definition")"
valkey="$(jq -er '.containerDefinitions[]|select(.name=="valkey").image' <<< "$definition")"
file="$RUNNER_TEMP/amaris-private-task.json"
python3 deploy/aws/ecs/render-task.py "$STAGING_ADDRESS" "$role" "$nginx" "$valkey" \
  | python3 deploy/aws/vpc/render-private-task.py > "$file"
revision_key="$(jq -cS . "$file" | sha256sum | cut -d' ' -f1)"
network="$(jq -cn --arg primary "$STAGING_PRIVATE_PRIMARY" --arg secondary "$STAGING_PRIVATE_SECONDARY" \
  --arg sg "$STAGING_PRIVATE_SG" '{awsvpcConfiguration:{subnets:[$primary,$secondary],securityGroups:[$sg],assignPublicIp:"DISABLED"}}')"
service="$(aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$PRIVATE_SERVICE" \
  --query 'services[?status==`ACTIVE`] | [0]' --output json)"
task="$(jq -r '.taskDefinition // empty' <<< "$service")"
current=''
if [[ -n "$task" ]]; then
  current="$(aws ecs describe-task-definition --task-definition "$task" --include TAGS \
    --query 'tags[?key==`ConfigurationSha256`].value | [0]' --output text)"
fi
if [[ "$current" != "$revision_key" ]]; then
  task="$(aws ecs register-task-definition --cli-input-json "file://$file" \
    --tags "key=ConfigurationSha256,value=$revision_key" --query taskDefinition.taskDefinitionArn --output text)"
fi
[[ "$task" == arn:aws:ecs:eu-north-1:110156539003:task-definition/amaris-ecs-staging-private-web:* ]]
if [[ "$(jq -r '.status // empty' <<< "$service")" != ACTIVE ]]; then
  aws ecs create-service --cluster "$ECS_CLUSTER" --service-name "$PRIVATE_SERVICE" \
    --task-definition "$task" --desired-count 1 --launch-type EC2 --network-configuration "$network" \
    --deployment-configuration 'minimumHealthyPercent=0,maximumPercent=100,deploymentCircuitBreaker={enable=true,rollback=true}' \
    --query service.serviceName --output text
elif [[ "$task" != "$(jq -r .taskDefinition <<< "$service")" || "$(jq -r .desiredCount <<< "$service")" != 1 ]]; then
  aws ecs update-service --cluster "$ECS_CLUSTER" --service "$PRIVATE_SERVICE" --task-definition "$task" --desired-count 1 \
    --network-configuration "$network" --query service.serviceName --output text
fi
printf 'STAGING_PRIVATE_TASK=%s\n' "$task" >> "$GITHUB_ENV"
