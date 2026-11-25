#!/usr/bin/env bash
set -euo pipefail

vpc_associations() {
  aws ec2 describe-vpcs --vpc-ids "$STAGING_VPC" --query 'Vpcs[0].Ipv6CidrBlockAssociationSet' --output json
}
association="$(vpc_associations | jq -r '[.[]? | select(.Ipv6CidrBlockState.State=="associated" or .Ipv6CidrBlockState.State=="associating")][0].AssociationId // empty')"
if [[ -z "$association" ]]; then
  association="$(aws ec2 associate-vpc-cidr-block --vpc-id "$STAGING_VPC" --amazon-provided-ipv6-cidr-block \
    --query Ipv6CidrBlockAssociation.AssociationId --output text)"
fi
[[ "$association" =~ ^vpc-cidr-assoc-[a-f0-9]+$ ]]
for attempt in {1..24}; do
  detail="$(vpc_associations | jq -c --arg id "$association" '.[]? | select(.AssociationId==$id)')"
  state="$(jq -r '.Ipv6CidrBlockState.State // empty' <<< "$detail")"
  if [[ "$state" == associated ]]; then break; fi
  if [[ "$state" == failed || "$state" == failing ]]; then
    echo '::error::AWS rejected the VPC IPv6 allocation.'
    exit 1
  fi
  sleep 4
done
if [[ "$state" != associated ]]; then
  printf '::error::The VPC IPv6 association did not become ready (last status %s).\n' "${state:-unavailable}"
  exit 1
fi
cidr="$(jq -er .Ipv6CidrBlock <<< "$detail")"
echo 'The VPC has an active IPv6 allocation.'
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
  if [[ "$state" != associated ]]; then
    printf '::error::Public subnet %s IPv6 association did not become ready (last status %s).\n' "$subnet" "$state"
    exit 1
  fi
  printf 'IPv6 allocation verified for public subnet %s.\n' "$subnet"
done
