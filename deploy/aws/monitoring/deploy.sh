#!/usr/bin/env bash
# Deploy only monitoring resources; no ECS, ALB or application changes.
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=""
if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]]; then
  export AWS_PROFILE="${AWS_PROFILE:-amaris}"
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$account" == "110156539003" ]] || { echo "Unexpected AWS account" >&2; exit 1; }
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
stack=amaris-staging-monitoring
if [[ -z "${OPERATOR_EMAIL:-}" ]]; then
  read -r -p "SNS notification email: " OPERATOR_EMAIL
fi
[[ "$OPERATOR_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || { echo "Invalid email address" >&2; exit 1; }
# Resolve current ECS service and live ALB target group, not a guessed resource ID.
status="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0].status' --output text)"
[[ "$status" == ACTIVE ]] || { echo "Expected an active staging ECS service" >&2; exit 1; }
target_arn="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0].loadBalancers[?containerName==`cms` && containerPort==`8080`].targetGroupArn | [0]' --output text)"
[[ "$target_arn" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:targetgroup/* ]] || { echo "Could not resolve the staging application target group" >&2; exit 1; }
alb_arn="$(aws elbv2 describe-target-groups --target-group-arns "$target_arn" --query 'TargetGroups[0].LoadBalancerArns[0]' --output text)"
[[ "$alb_arn" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:loadbalancer/app/* ]] || { echo "Could not resolve the expected staging ALB" >&2; exit 1; }
aws cloudformation validate-template --template-body "file://$script_dir/cloudwatch-sns.yml" >/dev/null
aws cloudformation deploy \
  --stack-name "$stack" \
  --template-file "$script_dir/cloudwatch-sns.yml" \
  --parameter-overrides "OperatorEmail=$OPERATOR_EMAIL" "ClusterName=$cluster" "ServiceName=$service" \
    "LoadBalancerFullName=${alb_arn#*loadbalancer/}" "ActiveTargetGroupFullName=targetgroup/${target_arn#*:targetgroup/}" \
  --no-fail-on-empty-changeset
topic="$(aws cloudformation describe-stacks --stack-name "$stack" --query 'Stacks[0].Outputs[?OutputKey==`AlarmTopicArn`].OutputValue | [0]' --output text)"
echo "SNS topic: $topic"
echo "Confirm the SNS subscription in the recipient inbox before testing delivery."
aws sns list-subscriptions-by-topic --topic-arn "$topic" --query 'Subscriptions[].{Protocol:Protocol,SubscriptionArn:SubscriptionArn}' --output table
