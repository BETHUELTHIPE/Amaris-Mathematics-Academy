#!/usr/bin/env bash
set -euo pipefail

subnets="$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$STAGING_VPC" --query Subnets --output json)"
jq -e --arg primary "$STAGING_PRIMARY_ZONE" --arg secondary "$STAGING_SECONDARY_ZONE" '
  length==4 and
  any(.CidrBlock=="10.86.0.0/26" and .AvailabilityZone==$primary) and
  any(.CidrBlock=="10.86.0.64/26" and .AvailabilityZone==$secondary) and
  any(.CidrBlock=="10.86.0.128/26" and .AvailabilityZone==$primary and .MapPublicIpOnLaunch==false) and
  any(.CidrBlock=="10.86.0.192/26" and .AvailabilityZone==$secondary and .MapPublicIpOnLaunch==false)
' <<< "$subnets"
routes="$(aws ec2 describe-route-tables --route-table-ids "$STAGING_PUBLIC_ROUTES" "$STAGING_PRIVATE_ROUTES" \
  --query RouteTables --output json)"
jq -e --arg public "$STAGING_PUBLIC_ROUTES" --arg private "$STAGING_PRIVATE_ROUTES" \
  --arg pub1 "$STAGING_PUBLIC_SUBNET" --arg pub2 "$STAGING_PUBLIC_SECONDARY" \
  --arg priv1 "$STAGING_PRIVATE_PRIMARY" --arg priv2 "$STAGING_PRIVATE_SECONDARY" \
  --arg edge "$STAGING_INSTANCE" '
  (map(select(.RouteTableId==$public)) | first) as $pub |
  (map(select(.RouteTableId==$private)) | first) as $priv |
  ($pub.Associations | (map(.SubnetId) | sort)==([$pub1,$pub2]|sort)) and
  ($priv.Associations | (map(.SubnetId) | sort)==([$priv1,$priv2]|sort)) and
  ($pub.Routes | any(.DestinationCidrBlock=="0.0.0.0/0" and (.GatewayId|startswith("igw-")) and .State=="active")) and
  ($priv.Routes | any(.DestinationCidrBlock=="0.0.0.0/0" and .InstanceId==$edge and .State=="active")) and
  ($priv.Routes | all(((.GatewayId//"")|startswith("igw-"))|not))
' <<< "$routes"
jq -r 'sort_by(.CidrBlock)[] | [.SubnetId,.AvailabilityZone,.CidrBlock] | @tsv' <<< "$subnets"
