#!/usr/bin/env bash
set -euo pipefail
umask 077

account=110156539003
cluster=amaris-ecs-staging
web=amaris-web-staging-stateless
jobs=amaris-staging-singleton-jobs
origin=https://16.171.164.5
sha="${BACKEND_SHA:?Missing backend source}"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$account" ]]
curl -fsS --max-time 15 "$origin/health/version/" | jq -e --arg sha "$sha" '.git_sha == $sha' >/dev/null

state() {
  aws ecs describe-services --cluster "$cluster" --services "$1" --query 'services[0]' --output json
}

check_worker() {
  local revision="$1" state
  state="$(state "$jobs")" || return 1
  jq -e --arg revision "$revision" '
    .desiredCount == 1 and .runningCount == 1 and .pendingCount == 0 and
    .taskDefinition == $revision and
    (.deployments | length == 1 and .[0].rolloutState == "COMPLETED")
  ' <<< "$state" >/dev/null
}

web_state="$(state "$web")"
jq -e '.desiredCount == 2 and .runningCount == 2 and .pendingCount == 0 and
       (.deployments | length == 1 and .[0].rolloutState == "COMPLETED")' <<< "$web_state" >/dev/null
web_revision="$(jq -er .taskDefinition <<< "$web_state")"
aws ecs describe-task-definition --task-definition "$web_revision" --output json > "$work/web.json"
image="$(jq -er '.taskDefinition.containerDefinitions[] | select(.name == "backend") | .image' "$work/web.json")"
[[ "$image" =~ ^110156539003\.dkr\.ecr\.eu-north-1\.amazonaws\.com/amaris-staging-frontend@sha256:[a-f0-9]{64}$ ]]
jq -e --arg sha "$sha" '.taskDefinition.containerDefinitions[] | select(.name == "backend") |
    .entryPoint[2] | contains("export RELEASE_GIT_SHA="+$sha+"\nexport PAYSTACK_MODE=test\nexport PAYSTACK_ENABLED=false\n")' \
  "$work/web.json" >/dev/null
job_state="$(state "$jobs")"
previous="$(jq -er .taskDefinition <<< "$job_state")"
check_worker "$previous"
jq -e '.deploymentConfiguration.maximumPercent == 100 and .deploymentConfiguration.minimumHealthyPercent == 0' \
  <<< "$job_state" >/dev/null
aws ecs describe-task-definition --task-definition "$previous" --output json > "$work/worker.json"
jq -e '.taskDefinition | .family == "amaris-staging-singleton-jobs" and .networkMode == "awsvpc" and
       .runtimePlatform.cpuArchitecture == "ARM64" and
       ([.containerDefinitions[].name] | sort) == ["celery-beat","celery-worker"]' "$work/worker.json" >/dev/null

if ! jq -e --arg image "$image" '.taskDefinition.containerDefinitions | all(.image == $image)' \
  "$work/worker.json" >/dev/null; then
  jq --arg image "$image" '
    .taskDefinition |
    del(.taskDefinitionArn,.revision,.status,.requiresAttributes,.compatibilities,.registeredAt,.registeredBy,.deregisteredAt) |
    (.containerDefinitions[].image)=$image
  ' "$work/worker.json" > "$work/next.json"
  next="$(aws ecs register-task-definition --cli-input-json "file://$work/next.json" \
    --query taskDefinition.taskDefinitionArn --output text)"
  rollback() {
    local code=$?
    trap - EXIT
    if ((code != 0)) && [[ "$(state "$jobs" | jq -r .taskDefinition)" == "$next" ]]; then
      aws ecs update-service --cluster "$cluster" --service "$jobs" --task-definition "$previous" \
        --query service.taskDefinition --output text
      aws ecs wait services-stable --cluster "$cluster" --services "$jobs"
      check_worker "$previous" && echo "Verified recovery of the previous staging worker and Beat."
    fi
    rm -rf -- "$work"
    exit "$code"
  }
  trap rollback EXIT
  aws ecs update-service --cluster "$cluster" --service "$jobs" --task-definition "$next" \
    --query service.taskDefinition --output text
  aws ecs wait services-stable --cluster "$cluster" --services "$jobs"
fi
current="${next:-$previous}"
check_worker "$current"
task="$(aws ecs list-tasks --cluster "$cluster" --service-name "$jobs" --desired-status RUNNING \
  --query taskArns --output json | jq -er 'if length == 1 then .[0] else error("Expected one worker and Beat task") end')"
aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --output json |
  jq -e --arg revision "$current" --arg image "${image##*@}" '.tasks[0] |
    .taskDefinitionArn == $revision and .lastStatus == "RUNNING" and
    (.containers | length == 2 and all(.lastStatus == "RUNNING" and .imageDigest == $image))' >/dev/null
curl -fsS --max-time 15 "$origin/health/dependencies/" |
  jq -e '.dependencies.postgresql and .dependencies.redis' >/dev/null
echo "One staging Celery worker and one Beat process are running on the verified Paystack build."
