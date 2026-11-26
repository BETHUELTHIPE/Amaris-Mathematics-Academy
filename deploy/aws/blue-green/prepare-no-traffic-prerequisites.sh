#!/usr/bin/env bash
# Create only no-traffic blue-green prerequisites. Does not update ECS service/task or shift traffic.
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=""
export AWS_PROFILE="${AWS_PROFILE:-amaris}"
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
alb_stack=amaris-staging-alb
prereq_stack=amaris-staging-blue-green-prerequisites
routing_stack=amaris-staging-blue-green-routing
oidc_stack=amaris-staging-github-oidc-publisher
base="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$(aws sts get-caller-identity --query Account --output text)" == "110156539003" ]] || { echo "Unexpected AWS account; refusing." >&2; exit 1; }
svc="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount>0 and .runningCount==.desiredCount and .pendingCount==0 and (.deployments|length)==1' <<< "$svc" >/dev/null || { echo "Staging ECS service is not stable; refusing." >&2; exit 1; }
primary_tg="$(jq -er '.loadBalancers[]|select(.containerName=="cms" and .containerPort==8080).targetGroupArn' <<< "$svc")"
health="$(aws elbv2 describe-target-health --target-group-arn "$primary_tg" --output json)"
jq -e '(.TargetHealthDescriptions|length)>0 and all(.TargetHealthDescriptions[];.TargetHealth.State=="healthy")' <<< "$health" >/dev/null || { echo "Primary target group is not fully healthy; refusing." >&2; exit 1; }
alb_arn="$(aws cloudformation describe-stacks --stack-name "$alb_stack" --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerArn`].OutputValue | [0]' --output text)"
alb_details="$(aws elbv2 describe-load-balancers --load-balancer-arns "$alb_arn" --output json)"
vpc_id="$(jq -er '.LoadBalancers[0].VpcId' <<< "$alb_details")"
alb_dns="$(jq -er '.LoadBalancers[0].DNSName' <<< "$alb_details")"
alb_sgs="$(jq -r '.LoadBalancers[0].SecurityGroups[]' <<< "$alb_details")"
read -r -a alb_sg_array <<< "$alb_sgs"
[[ "${#alb_sg_array[@]}" -eq 1 ]] || { echo "Expected one ALB security group; review before proceeding." >&2; exit 1; }
alb_sg="${alb_sg_array[0]}"
mapfile -t alb_subnets < <(jq -r '.LoadBalancers[0].AvailabilityZones[].SubnetId' <<< "$alb_details")
[[ "${#alb_subnets[@]}" -eq 2 ]] || { echo "Expected two ALB subnets in two AZs." >&2; exit 1; }
subnets_json="$(aws ec2 describe-subnets --subnet-ids "${alb_subnets[@]}" --output json)"
jq -e '(.Subnets|length)==2 and all(.Subnets[]; any(.Ipv6CidrBlockAssociationSet[]?; .Ipv6CidrBlockState.State=="associated")) and ([.Subnets[].AvailabilityZone]|unique|length)==2' <<< "$subnets_json" >/dev/null || { echo "Both ALB subnets must have associated IPv6 CIDRs in separate AZs." >&2; exit 1; }
vpc_ipv6="$(aws ec2 describe-vpcs --vpc-ids "$vpc_id" --query 'Vpcs[0].Ipv6CidrBlockAssociationSet[?Ipv6CidrBlockState.State==`associated`].Ipv6CidrBlock | [0]' --output text)"
[[ "$vpc_ipv6" == */* ]] || { echo "VPC IPv6 CIDR is not associated." >&2; exit 1; }
listener_arn="$(aws elbv2 describe-listeners --load-balancer-arn "$alb_arn" --query 'Listeners[?Port==`80` && Protocol==`HTTP`].ListenerArn | [0]' --output text)"
[[ "$listener_arn" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:listener/app/* ]] || { echo "Expected the existing HTTP/80 listener." >&2; exit 1; }
rules="$(aws elbv2 describe-rules --listener-arn "$listener_arn" --output json)"
jq -e 'all(.Rules[];.IsDefault==true)' <<< "$rules" >/dev/null || { echo "Non-default listener rules already exist; review priorities before proceeding." >&2; exit 1; }
jq -e --arg tg "$primary_tg" '[.Rules[]|select(.IsDefault==true)|.Actions[]|select(.Type=="forward")|.TargetGroupArn] == [$tg]' <<< "$rules" >/dev/null || { echo "Default listener action is not a simple forward to the active primary target group." >&2; exit 1; }
echo "Validated stable service, healthy primary targets, ALB listener, VPC IPv6 and two IPv6 ALB subnets."
for template in \
  "$base/../iam/github-oidc-ecr-publisher.yml" \
  "$base/prerequisites.yml" \
  "$base/test-routing.yml"; do
  aws cloudformation validate-template --template-body "file://$template" >/dev/null
done
aws cloudformation deploy --stack-name "$oidc_stack" --template-file "$base/../iam/github-oidc-ecr-publisher.yml" --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset
aws cloudformation deploy --stack-name "$prereq_stack" --template-file "$base/prerequisites.yml" --parameter-overrides "VpcId=$vpc_id" --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset
alternate_tg="$(aws cloudformation describe-stacks --stack-name "$prereq_stack" --query 'Stacks[0].Outputs[?OutputKey==`AlternateTargetGroupArn`].OutputValue | [0]' --output text)"
[[ "$alternate_tg" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:targetgroup/* ]] || { echo "Alternate target group output missing." >&2; exit 1; }
aws cloudformation deploy \
  --stack-name "$routing_stack" \
  --template-file "$base/test-routing.yml" \
  --parameter-overrides \
    "ListenerArn=$listener_arn" \
    "PrimaryTargetGroupArn=$primary_tg" \
    "AlternateTargetGroupArn=$alternate_tg" \
    "VpcIpv6Cidr=$vpc_ipv6" \
    "VpcId=$vpc_id" \
    "AlbSecurityGroupId=$alb_sg" \
    "AlbDnsName=$alb_dns" \
    "TestSubnetA=${alb_subnets[0]}" \
    "TestSubnetB=${alb_subnets[1]}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
echo "No-traffic prerequisites created. ECS service, task definition, listener traffic weights and production traffic were not changed."
aws cloudformation describe-stacks --stack-name "$routing_stack" --query 'Stacks[0].Outputs' --output table
