#!/usr/bin/env bash
# Provision the one-node staging Valkey cache only after explicit cost approval.
# This does not update the running ECS service or task definition.
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=""
export AWS_PROFILE="${AWS_PROFILE:-amaris}"
if [[ "${CONFIRM_SHARED_VALKEY:-}" != "true" ]]; then
  echo "This creates one cache.t4g.micro Valkey node (approximately R205/month before tax, backups and data transfer)."
  echo "Review the cost, then rerun with CONFIRM_SHARED_VALKEY=true to provision."
  exit 2
fi
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
cache_stack=amaris-staging-shared-valkey
access_stack=amaris-staging-shared-valkey-access
base="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$(aws sts get-caller-identity --query Account --output text)" == "110156539003" ]] || { echo "Unexpected AWS account; refusing." >&2; exit 1; }
svc="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount>0 and .runningCount==.desiredCount and .pendingCount==0' <<< "$svc" >/dev/null || { echo "Staging service is not stable; refusing." >&2; exit 1; }
mapfile -t app_subnets < <(jq -r '.networkConfiguration.awsvpcConfiguration.subnets[]' <<< "$svc")
mapfile -t app_sgs < <(jq -r '.networkConfiguration.awsvpcConfiguration.securityGroups[]' <<< "$svc")
[[ "${#app_subnets[@]}" -eq 2 && "${#app_sgs[@]}" -eq 1 ]] || { echo "Expected exactly two application subnets and one application security group." >&2; exit 1; }
subnets="$(aws ec2 describe-subnets --subnet-ids "${app_subnets[@]}" --output json)"
jq -e '(.Subnets|length)==2 and ([.Subnets[].AvailabilityZone]|unique|length)==2 and all(.Subnets[];.MapPublicIpOnLaunch==false)' <<< "$subnets" >/dev/null || { echo "Cache subnets must be private subnets in separate AZs." >&2; exit 1; }
vpc_id="$(jq -er '.Subnets[0].VpcId' <<< "$subnets")"
[[ "$(jq -r '[.Subnets[].VpcId]|unique|length' <<< "$subnets")" == "1" ]] || { echo "Application subnets do not share a VPC." >&2; exit 1; }
alb_arn="$(aws cloudformation describe-stacks --stack-name amaris-staging-alb --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerArn`].OutputValue | [0]' --output text)"
alb_subnets="$(aws elbv2 describe-load-balancers --load-balancer-arns "$alb_arn" --query 'LoadBalancers[0].AvailabilityZones[].SubnetId' --output text)"
for subnet in "${app_subnets[@]}"; do
  [[ " $alb_subnets " != *" $subnet "* ]] || { echo "Refusing to use an ALB subnet for the cache." >&2; exit 1; }
done
task_arn="$(jq -er .taskDefinition <<< "$svc")"
task="$(aws ecs describe-task-definition --task-definition "$task_arn" --query taskDefinition --output json)"
execution_role_arn="$(jq -er .executionRoleArn <<< "$task")"
execution_role_name="${execution_role_arn##*/}"
[[ -n "$execution_role_name" ]] || { echo "Task execution role is missing." >&2; exit 1; }
aws cloudformation validate-template --template-body "file://$base/shared-valkey.yml" >/dev/null
aws cloudformation validate-template --template-body "file://$base/shared-valkey-access.yml" >/dev/null
aws cloudformation deploy \
  --stack-name "$cache_stack" \
  --template-file "$base/shared-valkey.yml" \
  --parameter-overrides \
    "VpcId=$vpc_id" \
    "PrivateSubnetA=${app_subnets[0]}" \
    "PrivateSubnetB=${app_subnets[1]}" \
    "ApplicationSecurityGroup=${app_sgs[0]}" \
    "CacheNodeType=cache.t4g.micro" \
  --no-fail-on-empty-changeset
aws cloudformation deploy \
  --stack-name "$access_stack" \
  --template-file "$base/shared-valkey-access.yml" \
  --parameter-overrides "ExecutionRoleName=$execution_role_name" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
outputs="$(aws cloudformation describe-stacks --stack-name "$cache_stack" --query 'Stacks[0].Outputs' --output json)"
endpoint="$(jq -er '.[]|select(.OutputKey=="PrimaryEndpoint")|.OutputValue' <<< "$outputs")"
port="$(jq -er '.[]|select(.OutputKey=="Port")|.OutputValue' <<< "$outputs")"
secret_arn="$(jq -er '.[]|select(.OutputKey=="AuthSecretArn")|.OutputValue' <<< "$outputs")"
password="$(aws secretsmanager get-secret-value --secret-id "$secret_arn" --query SecretString --output text)"
[[ "$password" =~ ^[A-Za-z0-9]+$ ]] || { unset password; echo "Unexpected secret format; refusing to create connection URLs." >&2; exit 1; }
tmp="$(mktemp)"
chmod 600 "$tmp"
trap 'rm -f "$tmp"; unset password url' EXIT
for spec in "cache:0" "public-cache:1" "broker:2" "result:3"; do
  name="${spec%%:*}"
  db="${spec##*:}"
  parameter="/amaris/aws-staging/shared-valkey/$name"
  url="rediss://:$password@$endpoint:$port/$db?ssl_cert_reqs=required"
  jq -n --arg name "$parameter" --arg value "$url" '{Name:$name,Type:"SecureString",Value:$value,Overwrite:true,Tier:"Standard",KeyId:"alias/aws/ssm"}' > "$tmp"
  aws ssm put-parameter --cli-input-json "file://$tmp" >/dev/null
done
unset password url
echo "Shared Valkey is provisioned and four SecureString parameters are ready."
echo "The running ECS service has NOT been updated; the stateless task migration remains a separate controlled release."
aws cloudformation describe-stacks --stack-name "$cache_stack" --query 'Stacks[0].Outputs[?OutputKey==`PrimaryEndpoint` || OutputKey==`Port`]' --output table
