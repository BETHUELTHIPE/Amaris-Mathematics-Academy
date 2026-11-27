#!/usr/bin/env bash
set -euo pipefail
cluster=amaris-ecs-staging
container_instances="$(aws ecs list-container-instances --cluster "$cluster" --query containerInstanceArns --output json)"
mapfile -t arns < <(jq -r '.[]' <<< "$container_instances")
(( ${#arns[@]} > 0 ))
nodes="$(aws ecs describe-container-instances --cluster "$cluster" --container-instances "${arns[@]}" --query 'containerInstances[?agentConnected].ec2InstanceId' --output json)"
# The public HTTPS gateway is also an Amaris log source.
mapfile -t hosts < <(jq -r '. + ["i-02855f007d15af597"] | unique[]' <<< "$nodes")
