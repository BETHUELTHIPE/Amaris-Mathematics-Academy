#!/usr/bin/env bash
set -euo pipefail
umask 077

account=110156539003
cluster=amaris-ecs-staging
web=amaris-web-staging-stateless
mode="${1:-probe}"
[[ "$mode" == probe || "$mode" == native ]]
stack="amaris-staging-paystack-green-${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}"
existing_stack=amaris-staging-ecs-second-host
origin=https://16.171.164.5
digest="sha256:bc67977a14b7f91bc5e095715d413367e84595666c96ba41e237e1820df88d30"
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$account" ]]
[[ "$(aws freetier get-account-plan-state --region us-east-1 --query accountPlanType --output text)" == FREE ]]
[[ "$(aws freetier get-account-plan-state --region us-east-1 --query accountPlanStatus --output text)" == ACTIVE ]]
aws ec2 describe-instance-types --filters Name=instance-type,Values=t4g.small Name=free-tier-eligible,Values=true \
  --query 'InstanceTypes[0].InstanceType' --output text | grep -qx t4g.small
aws ecr describe-images --repository-name amaris-staging-frontend --image-ids "imageDigest=$digest" \
  --query 'imageDetails[0].imageDigest' --output text | grep -Fxq "$digest"

service_state() {
  aws ecs describe-services --cluster "$cluster" --services "$web" --query 'services[0]' --output json
}

healthy() {
  if [[ "$mode" == native ]]; then
    python deploy/aws/paystack/staging-native-rollout.py check
    return
  fi
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
[[ "$health_sha" == cfdb105761836c7730fec52ada54c58c624206db ]]
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
stack_started=false
cleanup() {
  local result=$?
  trap - EXIT
  trap '' INT TERM
  if "$stack_started"; then
    # The probe stops its standalone tasks before returning. Check again before removing the host.
    local hosts registered running
    hosts="$(active_hosts)" || { echo "Temporary host retained: ECS status unavailable" >&2; exit 1; }
    registered="$(jq -r --arg host "$spare" '.[] | select(.ec2InstanceId == $host) | .containerInstanceArn' <<< "$hosts")"
    if [[ -n "$registered" ]]; then
      aws ecs update-container-instances-state --cluster "$cluster" --container-instances "$registered" \
        --status DRAINING --query 'containerInstances[0].status' --output text || exit 1
      local drained=false
      for attempt in {1..45}; do
        running="$(aws ecs list-tasks --cluster "$cluster" --container-instance "$registered" \
          --desired-status RUNNING --query 'taskArns' --output json)" || exit 1
        if jq -e 'length == 0' <<< "$running" >/dev/null && healthy; then
          drained=true
          break
        fi
        sleep 10
      done
      if [[ "$drained" != true ]]; then
        echo "Temporary host retained: drain and staging health could not both be verified." >&2
        exit 1
      fi
      aws ecs deregister-container-instance --cluster "$cluster" --container-instance "$registered" \
        --query 'containerInstance.status' --output text || exit 1
    fi
    aws cloudformation delete-stack --stack-name "$stack" || exit 1
    aws cloudformation wait stack-delete-complete --stack-name "$stack" || exit 1
    echo "PASS: temporary t4g.small stack and encrypted root volume removed."
  fi
  healthy || exit 1
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# The run-specific stack name prevents deleting or adopting an unrelated host.
python deploy/aws/paystack/staging-green-probe.py preflight
stack_started=true
aws cloudformation deploy --stack-name "$stack" --template-file deploy/aws/paystack/staging-green-host.yml \
  --parameter-overrides "VpcId=$vpc" "PrivateSubnet=$subnet" "InstanceProfileName=$profile" "ImageId=$ami" "RootDevice=$device" \
  --tags Project=Amaris Environment=staging Purpose=paystack-green-validation
spare="$(aws cloudformation describe-stacks --stack-name "$stack" \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue | [0]' --output text)"
[[ "$spare" =~ ^i-[a-f0-9]+$ && "$spare" != "$private" ]]
for attempt in {1..30}; do
  hosts="$(active_hosts)"
  if jq -e --arg spare "$spare" 'any(.[]; .ec2InstanceId == $spare and .agentConnected and
    any(.attributes[]; .name == "ecs.capability.task-eni"))' <<< "$hosts" >/dev/null; then
    break
  fi
  if ((attempt == 30)); then
    echo "Temporary host did not register with ECS." >&2
    exit 1
  fi
  sleep 8
done
healthy
echo "PASS: private Free plan-eligible t4g.small connected to staging ECS."
if [[ "$mode" == native ]]; then
  python deploy/aws/paystack/staging-native-rollout.py "$spare"
else
  python deploy/aws/paystack/staging-green-probe.py "$spare"
fi
