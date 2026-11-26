#!/usr/bin/env bash
set -euo pipefail

export AWS_DEFAULT_REGION=eu-north-1 AWS_REGION=eu-north-1 AWS_PAGER=""
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
root="$(dirname "${BASH_SOURCE[0]}")"
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]

state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount==.runningCount and .pendingCount==0' <<< "$state" >/dev/null
revision="$(jq -er .taskDefinition <<< "$state")"
candidate="$(aws ecs describe-task-definition --task-definition "$revision" --query taskDefinition --output json |
  python3 "$root/render-stateless-task.py" --reuse-current-proxy)"
jq -e '(.volumes | length) == 0 and (.containerDefinitions | length) == 3 and
  all(.containerDefinitions[]; .name != "valkey" and ((.mountPoints // []) | length) == 0)' \
  <<< "$candidate" >/dev/null

proxy="$(jq -er '.containerDefinitions[] | select(.name == "cms") | .image' <<< "$candidate")"
command="$(jq -er '.containerDefinitions[] | select(.name == "cms") | .command[0]' <<< "$candidate")"
start="exec /docker-entrypoint.sh nginx -g 'daemon off;'"
[[ "$command" == *"$start" ]]
docker run --rm --platform linux/arm64 --entrypoint /bin/sh "$proxy" -ec "${command%"$start"}exec nginx -t"

ids="$(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output text)"
[[ -n "$ids" && "$ids" != None ]]
read -r -a instances <<< "$ids"
hosts="$(aws ecs describe-container-instances --cluster "$cluster" --container-instances "${instances[@]}" --output json)"
jq -e '(.failures | length) == 0' <<< "$hosts" >/dev/null

parameters="$(aws ssm describe-parameters --parameter-filters \
  Key=Name,Option=BeginsWith,Values=/amaris/aws-staging/shared-valkey/ \
  --query 'Parameters[?Type==`SecureString`].Name' --output json)"

{
  echo 'The live release rendered as a stateless task with zero host mounts. The pinned ARM64 Nginx image passed nginx -t with the embedded configuration.'
  jq -r '"Active ECS service tasks: \(.runningCount)."' <<< "$state"
  jq -r '"Connected ECS hosts: \([.containerInstances[] | select(.agentConnected)] | length)."' <<< "$hosts"
  jq -r '"Required shared Valkey SecureString parameters present: \([.[] | select(test("/(cache|public-cache|broker|result)$"))] | unique | length)/4."' <<< "$parameters"
  jq -r '[.containerDefinitions[] | .memoryReservation // .memory] | add | "Candidate memory reservation per task: \(.) MiB."' <<< "$candidate"
  echo 'The candidate was rendered and tested without registering a task or adding AWS resources.'
} | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
