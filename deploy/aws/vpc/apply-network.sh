#!/usr/bin/env bash
set -euo pipefail

egress="${1:-false}"
[[ "$egress" == false || "$egress" == true ]]
aws cloudformation validate-template --template-body file://deploy/aws/vpc/network.yml --query Description --output text
aws cloudformation deploy --stack-name "$NET_STACK" --template-file deploy/aws/vpc/network.yml \
  --no-fail-on-empty-changeset --parameter-overrides \
  "VpcId=$STAGING_VPC" "PublicRouteTableId=$STAGING_PUBLIC_ROUTES" \
  "EdgeSecurityGroupId=$STAGING_EDGE_SG" "EdgeInstanceId=$STAGING_INSTANCE" \
  "PrimaryZone=$STAGING_PRIMARY_ZONE" "SecondaryZone=$STAGING_SECONDARY_ZONE" "EnablePrivateEgress=$egress" \
  --tags Project=Amaris Environment=staging
outputs="$(aws cloudformation describe-stacks --stack-name "$NET_STACK" --query 'Stacks[0].Outputs' --output json)"
read_output() { jq -er --arg key "$1" '.[] | select(.OutputKey==$key).OutputValue' <<< "$outputs"; }
{
  printf 'STAGING_PUBLIC_SECONDARY=%s\n' "$(read_output SecondPublicSubnet)"
  printf 'STAGING_PRIVATE_PRIMARY=%s\n' "$(read_output PrimaryPrivateSubnet)"
  printf 'STAGING_PRIVATE_SECONDARY=%s\n' "$(read_output SecondaryPrivateSubnet)"
  printf 'STAGING_PRIVATE_ROUTES=%s\n' "$(read_output PrivateRouteTable)"
  printf 'STAGING_PRIVATE_SG=%s\n' "$(read_output PrivateTaskSecurityGroup)"
} >> "$GITHUB_ENV"
