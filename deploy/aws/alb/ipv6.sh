#!/usr/bin/env bash
set -euo pipefail

cidr="$(aws ec2 describe-vpcs --vpc-ids "$STAGING_VPC" \
  --query 'Vpcs[0].Ipv6CidrBlockAssociationSet[?Ipv6CidrBlockState.State==`associated` || Ipv6CidrBlockState.State==`associating`].Ipv6CidrBlock | [0]' --output text)"
if [[ "$cidr" == None ]]; then
  cidr="$(aws ec2 associate-vpc-cidr-block --vpc-id "$STAGING_VPC" --amazon-provided-ipv6-cidr-block \
    --query Ipv6CidrBlockAssociation.Ipv6CidrBlock --output text)"
fi
for attempt in {1..30}; do
  state="$(aws ec2 describe-vpcs --vpc-ids "$STAGING_VPC" --query Vpcs --output json | \
    jq -r --arg cidr "$cidr" '.[0].Ipv6CidrBlockAssociationSet[] | select(.Ipv6CidrBlock==$cidr).Ipv6CidrBlockState.State')"
  [[ "$state" != failed ]]
  if [[ "$state" == associated ]]; then break; fi
  sleep 3
done
[[ "$state" == associated ]]
read -r a b <<< "$(python3 -c 'import ipaddress,sys; blocks=ipaddress.IPv6Network(sys.argv[1]).subnets(new_prefix=64); print(next(blocks),next(blocks))' "$cidr")"
for index in 1 2; do
  if [[ "$index" == 1 ]]; then subnet="$STAGING_PUBLIC_SUBNET"; block="$a"; else subnet="$STAGING_PUBLIC_SECONDARY"; block="$b"; fi
  details="$(aws ec2 describe-subnets --subnet-ids "$subnet" --query 'Subnets[0].Ipv6CidrBlockAssociationSet' --output json)"
  if ! jq -e --arg block "$block" 'any(.Ipv6CidrBlock==$block and (.Ipv6CidrBlockState.State=="associated" or .Ipv6CidrBlockState.State=="associating"))' <<< "$details" >/dev/null; then
    jq -e 'length==0' <<< "$details" >/dev/null
    aws ec2 associate-subnet-cidr-block --subnet-id "$subnet" --ipv6-cidr-block "$block" --query SubnetId --output text
  fi
  for attempt in {1..30}; do
    state="$(aws ec2 describe-subnets --subnet-ids "$subnet" --query 'Subnets[0].Ipv6CidrBlockAssociationSet[0].Ipv6CidrBlockState.State' --output text)"
    [[ "$state" != failed ]]
    if [[ "$state" == associated ]]; then break; fi
    sleep 3
  done
  [[ "$state" == associated ]]
done
