#!/usr/bin/env bash
set -euo pipefail

private="$(aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$PRIVATE_SERVICE" \
  --query 'services[0].taskDefinition' --output text)"
[[ "$private" == arn:aws:ecs:eu-north-1:110156539003:task-definition/amaris-ecs-staging-private-web:* ]]
definition="$(aws ecs describe-task-definition --task-definition "$private" --query taskDefinition --output json)"
role="$(jq -er .executionRoleArn <<< "$definition")"
nginx="$(jq -er '.containerDefinitions[]|select(.name=="cms").image' <<< "$definition")"
valkey="$(jq -er '.containerDefinitions[]|select(.name=="valkey").image' <<< "$definition")"
file="$RUNNER_TEMP/amaris-alb-task.json"
python3 deploy/aws/ecs/render-task.py "$STAGING_ADDRESS" "$role" "$nginx" "$valkey" \
  | python3 deploy/aws/vpc/render-private-task.py | python3 deploy/aws/alb/render-task.py > "$file"
key="$(jq -cS . "$file" | sha256sum | cut -d' ' -f1)"
net="$(jq -cn --arg a "$STAGING_PRIVATE_PRIMARY" --arg b "$STAGING_PRIVATE_SECONDARY" \
  --arg sg "$STAGING_PRIVATE_SG" '{awsvpcConfiguration:{subnets:[$a,$b],securityGroups:[$sg],assignPublicIp:"DISABLED"}}')"
load_balancer="$(jq -cn --arg arn "$STAGING_TARGET_ARN" '[{targetGroupArn:$arn,containerName:"cms",containerPort:8080}]')"
service="$(aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$ALB_SERVICE" \
  --query 'services[?status==`ACTIVE`] | [0]' --output json)"
task="$(jq -r '.taskDefinition // empty' <<< "$service")"
current=''
if [[ -n "$task" ]]; then
  current="$(aws ecs describe-task-definition --task-definition "$task" --include TAGS \
    --query 'tags[?key==`ConfigurationSha256`].value | [0]' --output text)"
fi
if [[ "$current" != "$key" ]]; then
  task="$(aws ecs register-task-definition --cli-input-json "file://$file" \
    --tags "key=ConfigurationSha256,value=$key" --query taskDefinition.taskDefinitionArn --output text)"
fi
[[ "$task" == arn:aws:ecs:eu-north-1:110156539003:task-definition/amaris-ecs-staging-alb-web:* ]]
if [[ "$(jq -r '.status // empty' <<< "$service")" != ACTIVE ]]; then
  aws ecs create-service --cluster "$ECS_CLUSTER" --service-name "$ALB_SERVICE" \
    --task-definition "$task" --desired-count 1 --launch-type EC2 --network-configuration "$net" \
    --load-balancers "$load_balancer" --health-check-grace-period-seconds 120 \
    --deployment-configuration 'minimumHealthyPercent=0,maximumPercent=100,deploymentCircuitBreaker={enable=true,rollback=true}' \
    --query service.serviceName --output text
elif [[ "$task" != "$(jq -r .taskDefinition <<< "$service")" || "$(jq -r .desiredCount <<< "$service")" != 1 ]]; then
  aws ecs update-service --cluster "$ECS_CLUSTER" --service "$ALB_SERVICE" --task-definition "$task" --desired-count 1 \
    --network-configuration "$net" --query service.serviceName --output text
fi
