#!/usr/bin/env bash
set -euo pipefail
umask 077

account=110156539003
cluster=amaris-ecs-staging
service=amaris-web-staging-stateless
origin=https://16.171.164.5
baseline=cfdb105761836c7730fec52ada54c58c624206db
sha="${BACKEND_SHA:?Missing backend source}"
digest="${BACKEND_DIGEST:?Missing backend digest}"
registry="$account.dkr.ecr.eu-north-1.amazonaws.com/amaris-staging-frontend"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
[[ "$(aws sts get-caller-identity --query Account --output text)" == "$account" ]]
[[ "$sha" =~ ^[a-f0-9]{40}$ && "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]

service_state() {
  aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json
}

health() {
  local expected="$1"
  local state targets
  state="$(service_state)" || return 1
  jq -e --arg rev "$expected" '
    .status == "ACTIVE" and .taskDefinition == $rev and
    .desiredCount == 2 and .runningCount == 2 and .pendingCount == 0 and
    (.deployments | length == 1 and .[0].rolloutState == "COMPLETED")
  ' <<< "$state" >/dev/null || return 1
  targets="$(aws elbv2 describe-target-health --target-group-arn "$target" --output json)" || return 1
  jq -e '[.TargetHealthDescriptions[] | select(.TargetHealth.State == "healthy")] | length == 2' \
    <<< "$targets" >/dev/null || return 1
  curl --fail --silent --show-error --retry 1 --max-time 15 "$origin/health/dependencies/" |
    jq -e '.dependencies.postgresql and .dependencies.redis' >/dev/null
}

state="$(service_state)"
previous="$(jq -er .taskDefinition <<< "$state")"
target="$(jq -er '.loadBalancers[] | select(.containerName == "cms").targetGroupArn' <<< "$state")"
[[ "$previous" == arn:aws:ecs:eu-north-1:"$account":task-definition/amaris-ecs-staging-alb-web:* ]]
[[ "$target" == arn:aws:elasticloadbalancing:eu-north-1:"$account":targetgroup/amaris-staging-stateless/* ]]
jq -e '.deploymentController.type == "ECS" and
       (.deploymentConfiguration.strategy // "ROLLING") == "ROLLING" and
       .deploymentConfiguration.minimumHealthyPercent == 100 and
       .deploymentConfiguration.maximumPercent >= 150 and
       .deploymentConfiguration.deploymentCircuitBreaker.rollback and
       .deploymentConfiguration.alarms.enable and .deploymentConfiguration.alarms.rollback' \
  <<< "$state" >/dev/null
health "$previous"
current="$(curl -fsS --max-time 15 "$origin/health/version/" | jq -er .git_sha)"
if [[ "$current" == "$sha" ]]; then
  echo "The exact Paystack-compatible backend is already healthy."
elif [[ "$current" != "$baseline" ]]; then
  echo "Another staging backend has deployed since this candidate was built." >&2
  exit 1
fi
network="$(jq -cer '.networkConfiguration | select(.awsvpcConfiguration.assignPublicIp == "DISABLED")' <<< "$state")"

if [[ "$current" != "$sha" ]]; then
  aws ecs describe-task-definition --task-definition "$previous" --output json > "$work/previous.json"
  jq --arg image "$registry@$digest" --arg sha "$sha" '
    .taskDefinition |
    if .family != "amaris-ecs-staging-alb-web" or .networkMode != "awsvpc" or
       .runtimePlatform.cpuArchitecture != "ARM64" or
       ([.containerDefinitions[].name] | sort) != ["backend","cms","frontend"] then
      error("Unexpected staging task definition")
    else . end |
    del(.taskDefinitionArn,.revision,.status,.requiresAttributes,.compatibilities,.registeredAt,.registeredBy,.deregisteredAt) |
    (.containerDefinitions[] | select(.name == "backend")) |= (
      .image=$image |
      .entryPoint[2] |= (
        gsub("export RELEASE_GIT_SHA=[a-f0-9]{40}\n"; "") |
        split("exec \"$@\"") |
        if length == 2 then
          join("export RELEASE_GIT_SHA="+$sha+"\nexport PAYSTACK_MODE=test\nexport PAYSTACK_ENABLED=false\nexec \"$@\"")
        else error("Unexpected backend runtime entry point") end
      )
    )
  ' "$work/previous.json" > "$work/web.json"
  jq --rawfile migration deploy/aws/paystack/migrate.py '
    .family="amaris-ecs-staging-paystack-migration" | del(.placementConstraints,.cpu,.memory) |
    .containerDefinitions |= map(select(.name == "backend") |
      del(.healthCheck,.dependsOn,.portMappings) | .command=["python","manage.py","shell","-c",$migration])
  ' "$work/web.json" > "$work/migration.json"
  migration="$(aws ecs register-task-definition --cli-input-json "file://$work/migration.json" \
    --query taskDefinition.taskDefinitionArn --output text)"
  attempt="$(aws ecs run-task --cluster "$cluster" --task-definition "$migration" --launch-type EC2 --count 1 \
    --network-configuration "$network" --started-by amaris-staging-paystack --output json)"
  task="$(jq -er 'select(.failures == [] and (.tasks | length == 1)) | .tasks[0].taskArn' <<< "$attempt")"
  aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task"
  aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --output json |
    jq -e '.tasks[0].containers | length == 1 and .[0].exitCode == 0' >/dev/null
  echo "Applied the additive Paystack migration to the staging database."
  health "$previous"

  next="$(aws ecs register-task-definition --cli-input-json "file://$work/web.json" \
    --query taskDefinition.taskDefinitionArn --output text)"
  rollback() {
    local code=$?
    trap - EXIT
    if ((code != 0)) && [[ "$(service_state | jq -r .taskDefinition)" == "$next" ]]; then
      aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$previous" \
        --query service.taskDefinition --output text
      aws ecs wait services-stable --cluster "$cluster" --services "$service"
      health "$previous" && echo "Verified recovery of both previous staging replicas."
    fi
    rm -rf -- "$work"
    exit "$code"
  }
  trap rollback EXIT
  aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$next" \
    --query service.taskDefinition --output text
  aws ecs wait services-stable --cluster "$cluster" --services "$service"
  health "$next"
fi
curl -fsS --max-time 15 "$origin/health/version/" | jq -e --arg sha "$sha" '.git_sha == $sha' >/dev/null
curl -fsS --max-time 15 "$origin/" -o /dev/null
webhook="$origin/api/v1/paystack/webhook/"
[[ "$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' "$webhook")" == 405 ]]
[[ "$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' -X POST "$webhook")" == 403 ]]
aws ecs describe-task-definition --task-definition "${next:-$previous}" --output json |
  jq -e '.taskDefinition.containerDefinitions[] | select(.name == "backend") |
    .entryPoint[2] | contains("export PAYSTACK_MODE=test\nexport PAYSTACK_ENABLED=false\n")' >/dev/null
echo "Verified the new AWS staging webhook with both healthy replicas and Paystack checkout disabled."
