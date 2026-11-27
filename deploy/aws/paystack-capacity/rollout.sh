#!/usr/bin/env bash
set -euo pipefail
umask 077

account=110156539003
cluster=amaris-ecs-staging
web=amaris-web-staging-stateless
stack=amaris-staging-paystack-rollout-spare
existing_stack=amaris-staging-ecs-second-host
origin=https://16.171.164.5
digest="${BACKEND_DIGEST:?Missing verified staging digest}"
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$account" ]]
[[ "$(aws freetier get-account-plan-state --region us-east-1 --query accountPlanType --output text)" == FREE ]]
aws ec2 describe-instance-types --filters Name=instance-type,Values=t4g.small Name=free-tier-eligible,Values=true \
  --query 'InstanceTypes[0].InstanceType' --output text | grep -qx t4g.small
aws ecr describe-images --repository-name amaris-staging-frontend --image-ids "imageDigest=$digest" \
  --query 'imageDetails[0].imageDigest' --output text | grep -Fxq "$digest"

service_state() {
  aws ecs describe-services --cluster "$cluster" --services "$web" --query 'services[0]' --output json
}

healthy() {
  local state
  state="$(service_state)" || return 1
  jq -e '.desiredCount == 2 and .runningCount == 2 and .pendingCount == 0 and
    (.deployments | length == 1 and .[0].rolloutState == "COMPLETED")' <<< "$state" >/dev/null || return 1
  aws elbv2 describe-target-health --target-group-arn "$target" --output json |
    jq -e '[.TargetHealthDescriptions[] | select(.TargetHealth.State == "healthy")] | length == 2' >/dev/null
}

active_hosts() {
  local hosts
  hosts="$(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output json)"
  mapfile -t active_arns < <(jq -r '.[]' <<< "$hosts")
  (("${#active_arns[@]}" > 0)) || return 1
  aws ecs describe-container-instances --cluster "$cluster" --container-instances "${active_arns[@]}" \
    --query containerInstances --output json
}

initial="$(service_state)"
target="$(jq -er '.loadBalancers[] | select(.containerName == "cms").targetGroupArn' <<< "$initial")"
[[ "$target" == arn:aws:elasticloadbalancing:eu-north-1:"$account":targetgroup/amaris-staging-stateless/* ]]
healthy
health_sha="$(curl -fsS --max-time 15 "$origin/health/version/" | jq -er .git_sha)"
if [[ "$health_sha" == "$BACKEND_SHA" ]]; then
  bash deploy/aws/paystack-worker/release.sh
  exit 0
fi
jq -e '.deploymentConfiguration.minimumHealthyPercent == 100 and
  .deploymentConfiguration.maximumPercent >= 150' <<< "$initial" >/dev/null
original_hosts="$(active_hosts)"
jq -e 'length == 2 and all(.[]; .agentConnected)' <<< "$original_hosts" >/dev/null

private="$(aws cloudformation describe-stacks --stack-name "$existing_stack" \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue | [0]' --output text)"
[[ "$private" =~ ^i-[a-f0-9]+$ ]]
jq -e --arg private "$private" 'any(.[]; .ec2InstanceId == $private)' <<< "$original_hosts" >/dev/null
host="$(aws ec2 describe-instances --instance-ids "$private" --query 'Reservations[0].Instances[0]' --output json)"
jq -e '.VpcId == "vpc-0252538d2febd4641" and .InstanceType == "t4g.small" and .PublicIpAddress == null' <<< "$host" >/dev/null
vpc="$(jq -er .VpcId <<< "$host")"
subnet="$(jq -er .SubnetId <<< "$host")"
profile="$(jq -er '.IamInstanceProfile.Arn | split("/") | last' <<< "$host")"
ami="$(jq -er .ImageId <<< "$host")"
device="$(aws ec2 describe-images --image-ids "$ami" --owners amazon --filters Name=free-tier-eligible,Values=true --output json |
  jq -er '.Images[0] | .RootDeviceName as $root |
    select(.Architecture == "arm64" and .State == "available" and
    any(.BlockDeviceMappings[]; .DeviceName == $root and .Ebs.VolumeSize <= 30)) | $root')"
aws ec2 describe-subnets --subnet-ids "$subnet" --output json |
  jq -e --arg vpc "$vpc" '.Subnets[0] | .VpcId == $vpc and .AvailableIpAddressCount >= 5 and
    .MapPublicIpOnLaunch == false' >/dev/null
aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=$subnet" --output json |
  jq -e 'any(.RouteTables[].Routes[]; .DestinationCidrBlock == "0.0.0.0/0" and .State == "active" and
    .InstanceId == "i-02855f007d15af597")' >/dev/null

spare=""
spare_arn=""
stack_started=false
release_spare() {
  local result=$?
  trap - EXIT
  if [[ -n "$spare" && -z "$spare_arn" ]]; then
    discovered="$(active_hosts)" || discovered='[]'
    spare_arn="$(jq -r --arg id "$spare" '.[] | select(.ec2InstanceId == $id).containerInstanceArn' <<< "$discovered")"
  fi
  if [[ -n "$spare_arn" ]]; then
    if ! aws ecs update-container-instances-state --cluster "$cluster" \
         --container-instances "$spare_arn" --status DRAINING >/dev/null; then
      echo "Retained the spare host because ECS did not accept draining." >&2
      exit 1
    fi
    empty=false
    for attempt in {1..60}; do
      tasks="$(aws ecs list-tasks --cluster "$cluster" --container-instance "$spare_arn" \
        --desired-status RUNNING --query taskArns --output json)" || break
      if jq -e 'length == 0' <<< "$tasks" >/dev/null && healthy; then
        empty=true
        break
      fi
      sleep 8
    done
    if [[ "$empty" != true ]]; then
      echo "Retained the spare host because draining and two healthy targets could not both be verified." >&2
      exit 1
    fi
    aws ecs deregister-container-instance --cluster "$cluster" --container-instance "$spare_arn" >/dev/null
  fi
  if "$stack_started"; then
    aws cloudformation delete-stack --stack-name "$stack"
    aws cloudformation wait stack-delete-complete --stack-name "$stack"
    echo "Removed the temporary staging host and its encrypted root disk."
  fi
  if ((result == 0)); then
    remaining="$(active_hosts)"
    jq -e --argjson original "$original_hosts" '
      all(.[]; .agentConnected) and
      (map(.ec2InstanceId) | sort) == ($original | map(.ec2InstanceId) | sort)
    ' <<< "$remaining" >/dev/null
    healthy
    bash deploy/aws/paystack-worker/release.sh
  fi
  exit "$result"
}
trap release_spare EXIT
stack_started=true
aws cloudformation deploy --stack-name "$stack" --template-file deploy/aws/paystack-capacity/host.yml \
  --parameter-overrides "VpcId=$vpc" "PrivateSubnet=$subnet" "InstanceProfileName=$profile" "ImageId=$ami" "RootDevice=$device" \
  --no-fail-on-empty-changeset
spare="$(aws cloudformation describe-stacks --stack-name "$stack" \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue | [0]' --output text)"
[[ "$spare" =~ ^i-[a-f0-9]+$ && "$spare" != "$private" ]]
for attempt in {1..30}; do
  hosts="$(active_hosts)"
  spare_arn="$(jq -r --arg id "$spare" '.[] | select(.ec2InstanceId == $id and .agentConnected and
    any(.attributes[]; .name == "ecs.capability.task-eni") and
    any(.remainingResources[]; .name == "MEMORY" and .integerValue >= 600)).containerInstanceArn' <<< "$hosts")"
  [[ -n "$spare_arn" ]] && break
  sleep 10
done
[[ "$spare_arn" == arn:* ]]
healthy
echo "Verified a third private, Free Tier-eligible host while both original staging targets are healthy."
bash deploy/aws/paystack/release.sh
