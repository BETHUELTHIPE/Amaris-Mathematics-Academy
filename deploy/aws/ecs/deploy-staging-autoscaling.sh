#!/usr/bin/env bash
set -euo pipefail

export AWS_DEFAULT_REGION=eu-north-1 AWS_REGION=eu-north-1 AWS_PAGER=""
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
stack=amaris-staging-ecs-autoscaling
group=amaris-staging-ecs-asg
provider=amaris-staging-ec2-asg
template="$(dirname "${BASH_SOURCE[0]}")/staging-autoscaling.yml"

[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]] || {
  echo 'Unexpected AWS account.' >&2
  exit 1
}

read_service() {
  aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json
}

service_settings() {
  jq -cS '{taskDefinition,desiredCount,capacityProviderStrategy,loadBalancers,networkConfiguration}'
}

current="$(read_service)"
jq -e '.status == "ACTIVE" and .desiredCount > 0' <<< "$current" >/dev/null
original_settings="$(service_settings <<< "$current")"
mapfile -t subnets < <(jq -r '.networkConfiguration.awsvpcConfiguration.subnets[]' <<< "$current")
[[ "${#subnets[@]}" -eq 2 ]]
network="$(aws ec2 describe-subnets --subnet-ids "${subnets[@]}" --query Subnets --output json)"
jq -e 'length == 2 and ([.[].AvailabilityZone] | unique | length) == 2 and
  ([.[].VpcId] | unique | length) == 1 and all(.[]; .State == "available" and (.MapPublicIpOnLaunch | not))' \
  <<< "$network" >/dev/null
vpc="$(jq -er '.[0].VpcId' <<< "$network")"
for subnet in "${subnets[@]}"; do
  routes="$(aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=$subnet" \
    --query RouteTables --output json)"
  jq -e 'length == 1 and all(.[].Routes[]; ((.GatewayId // "") | startswith("igw-") | not)) and
    any(.[].Routes[]; .DestinationCidrBlock == "0.0.0.0/0" and .State == "active" and
      ((.NatGatewayId // .InstanceId // .NetworkInterfaceId // "") | test("^(nat|i|eni)-")))' \
    <<< "$routes" >/dev/null || { echo "Expected private IPv4 egress for $subnet." >&2; exit 1; }
done

host="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost \
  --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$host" =~ ^i-[0-9a-f]+$ ]]
profile="$(aws ec2 describe-instances --instance-ids "$host" \
  --query 'Reservations[0].Instances[0].IamInstanceProfile.Arn' --output text)"
[[ "$profile" == arn:aws:iam::110156539003:instance-profile/* ]]

aws cloudformation validate-template --template-body "file://$template" >/dev/null
aws cloudformation deploy --stack-name "$stack" --template-file "$template" --no-fail-on-empty-changeset \
  --parameter-overrides "StagingVpcId=$vpc" "PrivateSubnets=${subnets[0]},${subnets[1]}" "HostInstanceProfileArn=$profile"

cluster_state="$(aws ecs describe-clusters --clusters "$cluster" --query 'clusters[0]' --output json)"
jq -e '.status == "ACTIVE" and (.capacityProviders | type == "array") and
  (.defaultCapacityProviderStrategy | type == "array")' <<< "$cluster_state" >/dev/null
if ! jq -e --arg provider "$provider" '.capacityProviders | index($provider) != null' <<< "$cluster_state" >/dev/null; then
  input="$(jq -c --arg cluster "$cluster" --arg provider "$provider" '
    {cluster:$cluster,capacityProviders:(.capacityProviders + [$provider]),defaultCapacityProviderStrategy}' <<< "$cluster_state")"
  aws ecs put-cluster-capacity-providers --cli-input-json "$input" --query cluster.attachmentsStatus --output text
fi

for attempt in {1..30}; do
  if [[ "$(aws ecs describe-clusters --clusters "$cluster" --query 'clusters[0].attachmentsStatus' --output text)" == UPDATE_COMPLETE ]]; then
    break
  fi
  sleep 5
done
ready="$(aws ecs describe-clusters --clusters "$cluster" --query 'clusters[0]' --output json)"
jq -e --arg provider "$provider" --argjson previous "$cluster_state" '
  .attachmentsStatus == "UPDATE_COMPLETE" and (.capacityProviders | index($provider) != null) and
  ((.capacityProviders | sort) == (($previous.capacityProviders + [$provider]) | unique)) and
  (.defaultCapacityProviderStrategy == $previous.defaultCapacityProviderStrategy)' <<< "$ready" >/dev/null

asg="$(aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$group" \
  --query 'AutoScalingGroups[0]' --output json)"
jq -e --arg first "${subnets[0]}" --arg second "${subnets[1]}" '
  .MinSize == 0 and .MaxSize == 2 and (.VPCZoneIdentifier | split(",") | sort) == ([$first,$second] | sort) and
  .NewInstancesProtectedFromScaleIn and any(.Tags[]; .Key == "AmazonECSManaged")' <<< "$asg" >/dev/null
asg_arn="$(jq -er '.AutoScalingGroupARN' <<< "$asg")"
aws ecs describe-capacity-providers --capacity-providers "$provider" --query 'capacityProviders[0]' --output json \
  | jq -e --arg arn "$asg_arn" '.status == "ACTIVE" and (.autoScalingGroupProvider |
    .autoScalingGroupArn == $arn and .managedScaling.status == "ENABLED" and
    .managedDraining == "ENABLED" and .managedTerminationProtection == "ENABLED")' >/dev/null
aws autoscaling describe-policies --auto-scaling-group-name "$group" --query ScalingPolicies --output json \
  | jq -e 'any(.[]; .PolicyType == "TargetTrackingScaling" and .Enabled)' >/dev/null

[[ "$(read_service | service_settings)" == "$original_settings" ]] || {
  echo 'The live service settings changed during the operation. Inspect the ECS deployment history.' >&2
  exit 1
}

jq -r '"Auto Scaling group \(.AutoScalingGroupName): min \(.MinSize), desired \(.DesiredCapacity), max \(.MaxSize), instances \(.Instances | length)."' \
  <<< "$asg" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
printf 'ECS managed capacity provider %s is attached to %s. The running service settings were verified.\n' "$provider" "$cluster" \
  | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
