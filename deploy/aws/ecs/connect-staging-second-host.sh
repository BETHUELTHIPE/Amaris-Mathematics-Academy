#!/usr/bin/env bash
set -euo pipefail
trap 'echo "Staging host deployment check failed at line $LINENO." >&2' ERR

export AWS_DEFAULT_REGION=eu-north-1 AWS_REGION=eu-north-1 AWS_PAGER=""
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
stack=amaris-staging-ecs-second-host
root="$(dirname "${BASH_SOURCE[0]}")"

[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]] || {
  echo 'Unexpected AWS account.' >&2
  exit 1
}

read_service() {
  aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json
}

read_hosts() {
  local ids
  local -a arns
  ids="$(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output text)"
  [[ -n "$ids" && "$ids" != None ]] || return 1
  read -r -a arns <<< "$ids"
  aws ecs describe-container-instances --cluster "$cluster" --container-instances "${arns[@]}" --query containerInstances --output json
}

verify_healthy_target() {
  aws elbv2 describe-target-health --target-group-arn "$target_group" --output json |
    jq -e 'any(.TargetHealthDescriptions[]; .TargetHealth.State == "healthy")' >/dev/null
}

initial="$(read_service)"
jq -e '.status == "ACTIVE" and .desiredCount == 1 and .runningCount == 1 and .pendingCount == 0 and
  (.deployments | length) == 1 and (.loadBalancers | length) == 1' <<< "$initial" >/dev/null
target_group="$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$initial")"
verify_healthy_target

original_id="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost \
  --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$original_id" =~ ^i-[a-f0-9]+$ ]]
original="$(aws ec2 describe-instances --instance-ids "$original_id" --query 'Reservations[0].Instances[0]' --output json)"
vpc="$(jq -er .VpcId <<< "$original")"
zone="$(jq -er .Placement.AvailabilityZone <<< "$original")"
profile="$(jq -er '.IamInstanceProfile.Arn | split("/") | last' <<< "$original")"

subnet_ids="$(jq -er '.networkConfiguration.awsvpcConfiguration.subnets | join(" ")' <<< "$initial")"
read -r -a subnet_array <<< "$subnet_ids"
[[ "${#subnet_array[@]}" -eq 2 ]]
subnets="$(aws ec2 describe-subnets --subnet-ids "${subnet_array[@]}" --query Subnets --output json)"
subnet="$(jq -er --arg vpc "$vpc" --arg zone "$zone" '
  [.[] | select(.VpcId == $vpc and .AvailabilityZone != $zone and .State == "available" and
    (.MapPublicIpOnLaunch | not) and .AvailableIpAddressCount > 3)] | if length == 1 then .[0].SubnetId else error("Expected one private subnet in the other AZ") end
' <<< "$subnets")"
routes="$(aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=$subnet" --query RouteTables --output json)"
jq -e 'length == 1 and all(.[].Routes[]; ((.GatewayId // "") | startswith("igw-") | not)) and
  any(.[].Routes[]; .DestinationCidrBlock == "0.0.0.0/0" and .State == "active" and
    ((.NatGatewayId // .InstanceId // .NetworkInterfaceId // "") | test("^(nat|i|eni)-")))' <<< "$routes" >/dev/null

existing="$(aws cloudformation describe-stacks --stack-name "$stack" --query 'Stacks[0]' --output json 2>&1)" || {
  if [[ "$existing" == *'ValidationError'* && "$existing" == *'does not exist'* ]]; then
    existing=null
  else
    printf '%s\n' "$existing" >&2
    exit 1
  fi
}
hosts="$(read_hosts)"
jq -e --arg host "$original_id" 'any(.[]; .ec2InstanceId == $host and .agentConnected) and length <= 2' <<< "$hosts" >/dev/null

if [[ "$existing" == null ]]; then
  jq -e 'length == 1' <<< "$hosts" >/dev/null || { echo 'A second ECS host already exists.' >&2; exit 1; }
  serving_host="$(jq -er '.[0].containerInstanceArn' <<< "$hosts")"
  serving_task="$(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --desired-status RUNNING \
    --query taskArns --output json | jq -er 'if length == 1 then .[0] else error("Expected one service task") end')"
  aws ecs describe-tasks --cluster "$cluster" --tasks "$serving_task" --query 'tasks[0]' --output json |
    jq -e --arg host "$serving_host" '.containerInstanceArn == $host and .lastStatus == "RUNNING"' >/dev/null
  ami="$(aws ssm get-parameter --name /aws/service/ecs/optimized-ami/amazon-linux-2023/arm64/recommended/image_id \
    --query Parameter.Value --output text)"
  [[ "$ami" =~ ^ami-[a-f0-9]+$ ]]
  image="$(aws ec2 describe-images --image-ids "$ami" --query 'Images[0]' --output json)"
  device="$(jq -er '.RootDeviceName as $root | select(.Architecture == "arm64" and .State == "available" and
    any(.BlockDeviceMappings[]; .DeviceName == $root and .Ebs.VolumeSize <= 30)) | $root' <<< "$image")"

  task="$(aws ecs describe-task-definition --task-definition "$(jq -er .taskDefinition <<< "$initial")" --query taskDefinition --output json)"
  if jq -e 'any(.containerDefinitions[]; .name == "valkey") or any(.volumes[]?; (.host.sourcePath // "") != "")' <<< "$task" >/dev/null; then
    constraint="ec2InstanceId in ['$original_id']"
    aws ecs list-container-instances --cluster "$cluster" --filter "$constraint" --query containerInstanceArns --output json |
      jq -e 'length == 1' >/dev/null
    pin="$(jq -nc --arg expression "$constraint" '{type:"memberOf",expression:$expression}')"
    if ! jq -e --argjson pin "$pin" '.placementConstraints | index($pin) != null' <<< "$initial" >/dev/null; then
      constraints="$(jq -c --argjson pin "$pin" '(.placementConstraints // []) + [$pin]' <<< "$initial")"
      aws ecs update-service --cluster "$cluster" --service "$service" --placement-constraints "$constraints" \
        --query service.serviceName --output text >/dev/null
    fi
    jq -e --argjson pin "$pin" --argjson before "$initial" '.taskDefinition == $before.taskDefinition and
      ([.deployments[].id] == [$before.deployments[].id]) and (.placementConstraints | index($pin) != null)' \
      <<< "$(read_service)" >/dev/null
  fi
  verify_healthy_target
  aws cloudformation deploy --stack-name "$stack" --template-file "$root/staging-second-host.yml" \
    --parameter-overrides "VpcId=$vpc" "PrivateSubnet=$subnet" "InstanceProfileName=$profile" "ImageId=$ami" "RootDevice=$device" \
    --no-fail-on-empty-changeset || {
      aws cloudformation describe-stack-events --stack-name "$stack" \
        --query 'StackEvents[0:12].[LogicalResourceId,ResourceStatus,ResourceStatusReason]' --output table
      exit 1
    }
fi

second="$(aws cloudformation describe-stacks --stack-name "$stack" \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue | [0]' --output text)"
[[ "$second" =~ ^i-[a-f0-9]+$ && "$second" != "$original_id" ]]
aws ec2 wait instance-status-ok --instance-ids "$second"
aws ec2 describe-instances --instance-ids "$second" --query 'Reservations[0].Instances[0]' --output json |
  jq -e --arg subnet "$subnet" '.SubnetId == $subnet and .State.Name == "running" and .InstanceType == "t4g.small" and
    (.PublicIpAddress == null) and .MetadataOptions.HttpTokens == "required"' >/dev/null

for attempt in {1..30}; do
  hosts="$(read_hosts)"
  if jq -e --arg first "$original_id" --arg second "$second" 'length == 2 and
    all(.[]; .agentConnected) and any(.[]; .ec2InstanceId == $first) and
    any(.[]; .ec2InstanceId == $second and .runningTasksCount == 0 and .pendingTasksCount == 0 and
      any(.attributes[]; .name == "ecs.capability.task-eni"))' <<< "$hosts" >/dev/null; then
    verify_healthy_target
    jq -e --argjson before "$initial" '.taskDefinition == $before.taskDefinition and
      ([.deployments[].id] == [$before.deployments[].id]) and .runningCount == 1 and
      .desiredCount == 1 and .pendingCount == 0' <<< "$(read_service)" >/dev/null
    printf 'Two EC2 hosts are ACTIVE and connected to %s. The new host is private, with task ENI support. The ALB still reports a healthy service target.\n' "$cluster" |
      tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
    exit 0
  fi
  sleep 10
done
echo 'The second EC2 host has not satisfied the ECS registration checks.' >&2
exit 1
