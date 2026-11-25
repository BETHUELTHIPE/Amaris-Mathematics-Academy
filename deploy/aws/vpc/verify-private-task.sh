#!/usr/bin/env bash
set -euo pipefail

task_detail=''
for attempt in {1..38}; do
  service="$(aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$PRIVATE_SERVICE" --query 'services[0]' --output json)"
  if jq -e '.deployments | any(.rolloutState=="FAILED")' <<< "$service" >/dev/null; then
    echo '::error::The ECS private deployment circuit breaker reported a failure.'
    exit 1
  fi
  if jq -e --arg revision "$STAGING_PRIVATE_TASK" \
    '.taskDefinition==$revision and .runningCount==1 and .pendingCount==0 and (.deployments|length)==1' <<< "$service" >/dev/null; then
    arns="$(aws ecs list-tasks --cluster "$ECS_CLUSTER" --service-name "$PRIVATE_SERVICE" --desired-status RUNNING \
      --query taskArns --output text)"
    if [[ "$arns" == arn:aws:ecs:* ]]; then
      detail="$(aws ecs describe-tasks --cluster "$ECS_CLUSTER" --tasks $arns --output json)"
      if jq -e --arg revision "$STAGING_PRIVATE_TASK" \
        '.tasks | length==1 and all(.healthStatus=="HEALTHY" and .taskDefinitionArn==$revision and .lastStatus=="RUNNING")' \
        <<< "$detail" >/dev/null; then
        task_detail="$detail"
        break
      fi
    fi
  fi
  sleep 8
done
[[ -n "$task_detail" ]] || { echo '::error::The private ECS task did not become healthy.'; exit 1; }
interface="$(jq -er '.tasks[0].attachments[] | select(.type=="ElasticNetworkInterface" and .status=="ATTACHED") | .details[] | select(.name=="networkInterfaceId").value' <<< "$task_detail")"
[[ "$interface" =~ ^eni-[a-f0-9]+$ ]]
network="$(aws ec2 describe-network-interfaces --network-interface-ids "$interface" --query 'NetworkInterfaces[0]' --output json)"
jq -e --arg vpc "$STAGING_VPC" --arg primary "$STAGING_PRIVATE_PRIMARY" --arg secondary "$STAGING_PRIVATE_SECONDARY" \
  --arg sg "$STAGING_PRIVATE_SG" '
  .VpcId==$vpc and (.SubnetId==$primary or .SubnetId==$secondary) and (.Association.PublicIp|not)
  and (.Groups | map(.GroupId)==[$sg])
  ' <<< "$network"
address="$(jq -er .PrivateIpAddress <<< "$network")"
[[ "$address" =~ ^10\.86\.0\.[0-9]+$ ]]
jq -e --slurpfile expected "$RUNNER_TEMP/amaris-private-task.json" '
  .tasks[0].containers as $running | $expected[0].containerDefinitions |
  all(. as $want | $running | any(.name==$want.name and .lastStatus=="RUNNING" and .image==$want.image and
    (if .name=="frontend" or .name=="backend" then .imageDigest==($want.image | split("@")[1]) else true end)))
' <<< "$task_detail"
printf 'STAGING_PRIVATE_IP=%s\n' "$address" >> "$GITHUB_ENV"
printf 'Healthy ECS task %s has private address %s and no public IP.\n' \
  "$(jq -r '.tasks[0].taskArn|split("/")|last' <<< "$task_detail")" "$address"
