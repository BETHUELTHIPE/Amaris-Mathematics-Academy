#!/usr/bin/env bash
set -euo pipefail

[[ "$AWS_REGION" == eu-north-1 ]]
read -r account principal <<< "$(aws sts get-caller-identity --query '[Account,Arn]' --output text)"
[[ "$account" == 110156539003 && "$principal" != *:root ]]
stack_resource() {
  aws cloudformation describe-stack-resource --stack-name "$HOST_STACK" --logical-resource-id "$1" \
    --query StackResourceDetail.PhysicalResourceId --output text
}
vpc="$(stack_resource StagingVpc)"
public_subnet="$(stack_resource PublicSubnet)"
public_routes="$(stack_resource Routes)"
instance="$(stack_resource StagingHost)"
edge_sg="$(stack_resource WebSecurityGroup)"
address="$(aws cloudformation describe-stacks --stack-name "$HOST_STACK" \
  --query 'Stacks[0].Outputs[?OutputKey==`PublicIPv4`].OutputValue | [0]' --output text)"
[[ "$vpc" =~ ^vpc-[a-f0-9]+$ && "$public_subnet" =~ ^subnet-[a-f0-9]+$ && "$public_routes" =~ ^rtb-[a-f0-9]+$ ]]
[[ "$instance" =~ ^i-[a-f0-9]+$ && "$edge_sg" =~ ^sg-[a-f0-9]+$ && "$address" == 16.171.164.5 ]]
source="$(aws ec2 describe-subnets --subnet-ids "$public_subnet" --query 'Subnets[0]' --output json)"
jq -e --arg vpc "$vpc" '.VpcId==$vpc and .CidrBlock=="10.86.0.0/26"' <<< "$source" >/dev/null
primary="$(jq -r .AvailabilityZone <<< "$source")"
secondary="$(aws ec2 describe-availability-zones --query AvailabilityZones --output json | jq -r --arg primary "$primary" 'sort_by(.ZoneName) | map(select(.State=="available" and .ZoneName!=$primary and (.ZoneName|test("^eu-north-1[a-z]$")))) | first.ZoneName')"
[[ "$primary" != "$secondary" && "$primary" =~ ^eu-north-1[a-z]$ && "$secondary" =~ ^eu-north-1[a-z]$ ]]
aws ec2 describe-vpcs --vpc-ids "$vpc" --query 'Vpcs[0].CidrBlock' --output text | grep -Fxq 10.86.0.0/24
aws ec2 describe-instances --instance-ids "$instance" --query 'Reservations[0].Instances[0].State.Name' --output text | grep -Fxq running
if ! curl -fSs --connect-timeout 6 --max-time 10 "https://$address/health/ready/" | jq -e '.status=="ready"'; then
  echo '::warning::The existing HTTPS route is degraded. Verify host health and the ALB before switching traffic.'
fi
{
  printf 'STAGING_VPC=%s\n' "$vpc"
  printf 'STAGING_PUBLIC_SUBNET=%s\n' "$public_subnet"
  printf 'STAGING_PUBLIC_ROUTES=%s\n' "$public_routes"
  printf 'STAGING_INSTANCE=%s\n' "$instance"
  printf 'STAGING_EDGE_SG=%s\n' "$edge_sg"
  printf 'STAGING_ADDRESS=%s\n' "$address"
  printf 'STAGING_PRIMARY_ZONE=%s\n' "$primary"
  printf 'STAGING_SECONDARY_ZONE=%s\n' "$secondary"
} >> "$GITHUB_ENV"
