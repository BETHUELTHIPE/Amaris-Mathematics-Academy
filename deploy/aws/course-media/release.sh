#!/usr/bin/env bash
set -euo pipefail
umask 077

cluster=amaris-ecs-staging
service=amaris-web-staging-stateless
registry=110156539003.dkr.ecr.eu-north-1.amazonaws.com/amaris-staging-frontend
source_sha="${BACKEND_SHA:?Missing verified backend revision}"
origin=https://16.171.164.5
target_prefix=arn:aws:elasticloadbalancing:eu-north-1:110156539003:targetgroup/amaris-staging-stateless/
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT

[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]

service_state() {
  aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json
}

healthy_tasks() {
  local revision="$1" desired="$2" digest="${3:-}" ids listed details targets
  listed="$(aws ecs list-tasks --cluster "$cluster" --service-name "$service" \
    --desired-status RUNNING --query taskArns --output json)" || return 1
  mapfile -t ids < <(jq -r '.[]' <<< "$listed")
  if [[ "${#ids[@]}" != "$desired" ]]; then
    echo "ECS currently reports ${#ids[@]} of $desired expected tasks."
    return 1
  fi
  details="$(aws ecs describe-tasks --cluster "$cluster" --tasks "${ids[@]}" --query tasks --output json)" || return 1
  if ! jq -e --arg rev "$revision" --argjson desired "$desired" --arg digest "$digest" --arg backend "${BACKEND_DIGEST:-}" \
      'length == $desired and all(.[]; .taskDefinitionArn == $rev and
       .lastStatus == "RUNNING" and .healthStatus == "HEALTHY" and
       ($digest == "" or (any(.containers[]; .name == "frontend" and .imageDigest == $digest) and any(.containers[]; .name == "backend" and .imageDigest == $backend))))' <<< "$details" >/dev/null; then
    jq -c '[.[] | {lastStatus, healthStatus, revision: (.taskDefinitionArn | split("/") | last)}]' <<< "$details"
    return 1
  fi
  targets="$(aws elbv2 describe-target-health --target-group-arn "$target" --output json)" || return 1
  if ! jq -e --argjson desired "$desired" \
      '[.TargetHealthDescriptions[] | select(.TargetHealth.State == "healthy")] | length == $desired' <<< "$targets" >/dev/null; then
    jq -c '[.TargetHealthDescriptions[].TargetHealth | {State, Reason}]' <<< "$targets"
    return 1
  fi
}

public_health() {
  curl -fsS --retry 1 --max-time 15 "$origin/health/ready/" | jq -e '.status == "ready"' >/dev/null ||
    { echo 'Public Django readiness check failed.' >&2; return 1; }
  curl -fsS --retry 1 --max-time 15 "$origin/health/dependencies/" |
    jq -e '.dependencies.postgresql == true and .dependencies.redis == true' >/dev/null ||
    { echo 'Public PostgreSQL or Valkey health check failed.' >&2; return 1; }
  curl -fsS --retry 1 --max-time 15 "$origin/api/auth-state" |
    jq -e '.authenticated == false and .emailVerified == false' >/dev/null ||
    { echo 'Public anonymous frontend auth check failed.' >&2; return 1; }
  curl -fsS --retry 1 --max-time 15 "$origin/" -o "$work/home.html" &&
    grep -Fq 'Amaris Mathematics Academy' "$work/home.html" ||
    { echo 'Public homepage did not render.' >&2; return 1; }
}

stable_service() {
  jq -e --arg rev "$1" '
    .status == "ACTIVE" and .taskDefinition == $rev and .pendingCount == 0 and
    .runningCount == .desiredCount and
    any(.deployments[]; .status == "PRIMARY" and .taskDefinition == $rev and .rolloutState == "COMPLETED") and
    all(.deployments[]; .status == "PRIMARY" or (.runningCount == 0 and .pendingCount == 0))'
}

recovering_service() {
  jq -e --arg rev "$1" '
    .status == "ACTIVE" and .taskDefinition == $rev and .desiredCount == 2 and
    .runningCount >= 1 and .deploymentConfiguration.minimumHealthyPercent == 50 and
    .deploymentConfiguration.deploymentCircuitBreaker.rollback == true and
    all(.deployments[]; .taskDefinition == $rev) and
    any(.deployments[]; .rolloutState == "COMPLETED")'
}

healthy_recovery_target() {
  local target_status
  target_status="$(aws elbv2 describe-target-health --target-group-arn "$target" --output json)" || return 1
  jq -e 'any(.TargetHealthDescriptions[]; .TargetHealth.State == "healthy")' <<< "$target_status" >/dev/null
}

wait_until_healthy() {
  local revision="$1" digest="${2:-}" attempts="${3:-130}" current
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    current="$(service_state)" || return 1
    if stable_service "$revision" <<< "$current" >/dev/null && healthy_tasks "$revision" "$desired" "$digest"; then
      return 0
    fi
    if jq -e --arg rev "$revision" 'any(.deployments[]; .taskDefinition == $rev and .rolloutState == "FAILED")' \
       <<< "$current" >/dev/null || { [[ "$revision" != "$previous" ]] && [[ "$(jq -r .taskDefinition <<< "$current")" == "$previous" ]]; }; then
      echo 'ECS rejected the candidate rollout or started rollback.' >&2
      return 1
    fi
    if (( attempt % 6 == 1 )); then
      jq -c '{desiredCount, runningCount, pendingCount, deployments: [.deployments[] | {status, rolloutState, runningCount}]}' <<< "$current"
    fi
    sleep 8
  done
  echo "ECS monitoring timed out for ${revision##*/}." >&2
  return 1
}

state="$(service_state)"
previous="$(jq -er .taskDefinition <<< "$state")"
desired="$(jq -er .desiredCount <<< "$state")"
target="$(jq -er '.loadBalancers[] | select(.containerName == "cms" and .containerPort == 8080).targetGroupArn' <<< "$state")"
[[ "$target" == "$target_prefix"* && "$desired" == 2 ]]
jq -e '.deploymentController.type == "ECS" and
       (.deploymentConfiguration.strategy // "ROLLING") == "ROLLING" and
       .deploymentConfiguration.maximumPercent >= 100 and
       .deploymentConfiguration.minimumHealthyPercent >= 50 and
       (.deploymentConfiguration.minimumHealthyPercent <= 50 or .deploymentConfiguration.maximumPercent >= 150)' \
    <<< "$state" >/dev/null
ready=false
recovery=false
for attempt in {1..24}; do
  state="$(service_state)"
  if stable_service "$previous" <<< "$state" >/dev/null && healthy_tasks "$previous" "$desired" && public_health; then
    ready=true
    break
  fi
  if recovering_service "$previous" <<< "$state" >/dev/null && healthy_recovery_target && public_health; then
    ready=true
    recovery=true
    echo 'Staging recovery preflight passed with an available ALB target and the previous completed revision.'
    break
  fi
  jq -c '{desiredCount, runningCount, pendingCount, deployments: [.deployments[] | {status, rolloutState, runningCount}]}' <<< "$state"
  printf 'Preflight attempt %s of 24 is waiting for staging health.\n' "$attempt"
  sleep 8
done
if ! "$ready"; then
  echo 'Staging did not provide a protected rollback revision and a healthy public baseline.' >&2
  exit 1
fi
backend_sha="$(curl -fsS --max-time 15 "$origin/health/version/" | jq -er .git_sha)"
[[ "$backend_sha" =~ ^[0-9a-f]{40}$ ]]
jq -c '.deploymentConfiguration | {maximumPercent, minimumHealthyPercent, deploymentCircuitBreaker, alarms}' <<< "$state"
printf 'Preflight passed. Current rollback revision is %s.\n' "${previous##*/}"
printf 'Previous revision: `%s`\n\n' "${previous##*/}" >> "$GITHUB_STEP_SUMMARY"

[[ "$backend_sha" == 44e800ccc4ad4c0f88f5c6f7dde72907b06da19c ]]
[[ "$FRONTEND_DIGEST" =~ ^sha256:[a-f0-9]{64}$ && "$BACKEND_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]
[[ "$source_sha" =~ ^[a-f0-9]{40}$ ]]
outputs="$(aws cloudformation describe-stacks --stack-name amaris-staging-course-media   --query 'Stacks[0].Outputs' --output json)"
media_role="$(jq -er '.[] | select(.OutputKey=="TaskRoleArn").OutputValue' <<< "$outputs")"
media_bucket="$(jq -er '.[] | select(.OutputKey=="BucketName").OutputValue' <<< "$outputs")"
[[ "$media_role" == arn:aws:iam::110156539003:role/amaris-staging-course-media-* ]]
[[ "$media_bucket" == amaris-mathematics-academy-media-stage-110156539003-eu-north-1 ]]

aws ecs describe-task-definition --task-definition "$previous" --output json > "$work/previous.json"
jq -e '.taskDefinition as $t |
    $t.family=="amaris-ecs-staging-alb-web" and $t.networkMode=="awsvpc" and
    ($t.taskRoleArn // "")=="" and $t.runtimePlatform.cpuArchitecture=="ARM64" and
    ($t.volumes|length)==0 and ([$t.containerDefinitions[].name]|sort)==["backend","cms","frontend"] and
    ($t.containerDefinitions[] | select(.name=="backend").entryPoint[2] | contains("export DATABASE_CONN_MAX_AGE=0\n"))'   "$work/previous.json" > /dev/null

jq --arg back "$registry@$BACKEND_DIGEST" --arg front "$registry@$FRONTEND_DIGEST" --arg role "$media_role"    --arg bucket "$media_bucket" --arg sha "$source_sha" '
  .taskDefinition |
  del(.taskDefinitionArn,.revision,.status,.requiresAttributes,.compatibilities,.registeredAt,.registeredBy,.deregisteredAt) |
  .taskRoleArn=$role |
  (.containerDefinitions[]|select(.name=="frontend").image)=$front |
  (.containerDefinitions[]|select(.name=="backend")) |= (
    .image=$back |
    .environment=((.environment // []) + [{name:"ACADEMY_MEDIA_BUCKET",value:$bucket},{name:"ACADEMY_MEDIA_REGION",value:"eu-north-1"}]) |
    .entryPoint[2] |= (split("exec \"$@\"") |
      if length==2 then join("export RELEASE_GIT_SHA="+$sha+"\nexec \"$@\"") else error("Unexpected backend runtime wrapper") end)
  )
' "$work/previous.json" > "$work/web.json"
jq --rawfile migrate deploy/aws/course-media/migrate.py '
  .family="amaris-ecs-staging-course-media-migration" | del(.placementConstraints, .cpu, .memory) |
  .containerDefinitions |= map(select(.name=="backend") | del(.healthCheck,.dependsOn,.portMappings) |
    .command=["python","manage.py","shell","-c",$migrate])
' "$work/web.json" > "$work/migration.json"
migration="$(aws ecs register-task-definition --cli-input-json "file://$work/migration.json" --query taskDefinition.taskDefinitionArn --output text)"
network="$(jq -cer '.networkConfiguration | select(.awsvpcConfiguration.assignPublicIp=="DISABLED")' <<< "$state")"
aws ecs run-task --cluster "$cluster" --task-definition "$migration" --launch-type EC2 --count 1   --network-configuration "$network" --started-by amaris-staging-course-media --output json > "$work/migration-task.json"
migration_task="$(jq -er 'select((.failures|length)==0 and (.tasks|length)==1) | .tasks[0].taskArn' "$work/migration-task.json")"
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$migration_task"
aws ecs describe-tasks --cluster "$cluster" --tasks "$migration_task"   --query 'tasks[0].containers[].{name:name,exitCode:exitCode}' --output json |
  jq -e 'length==1 and .[0].name=="backend" and .[0].exitCode==0'
echo 'The one-off ECS task verified the staging database, media role and additive migration.'

state="$(service_state)"
stable_service "$previous" <<< "$state" >/dev/null
healthy_tasks "$previous" "$desired"
next="$(aws ecs register-task-definition --cli-input-json "file://$work/web.json"   --query taskDefinition.taskDefinitionArn --output text)"
[[ "$next" == "${previous%:*}:"* && "$next" != "$previous" ]]
rollback_on_failure() {
  local code=$? active
  trap - EXIT
  if (( code == 0 )) || [[ "$next" == "$previous" ]]; then
    rm -rf -- "$work"
    exit "$code"
  fi
  active="$(service_state | jq -r .taskDefinition)" || active=''
  if [[ "$active" == "$next" ]]; then
    aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$previous" \
      --query 'service.taskDefinition' --output text || echo 'Could not request the previous revision.' >&2
  fi
  if [[ "$active" == "$next" || "$active" == "$previous" ]] && wait_until_healthy "$previous" "" 90 && public_health; then
    printf 'Rollback verified: `%s` has two healthy ECS replicas.\n' "${previous##*/}" >> "$GITHUB_STEP_SUMMARY"
  else
    echo 'Automatic recovery could not verify the previous healthy revision.' >&2
  fi
  rm -rf -- "$work"
  exit "$code"
}
trap rollback_on_failure EXIT

aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$next"   --query service.taskDefinition --output text
wait_until_healthy "$next" "$FRONTEND_DIGEST"
public_health
curl -fsS --max-time 15 "$origin/health/version/" | jq -e --arg sha "$source_sha" '.git_sha==$sha' >/dev/null
curl -fsS --max-time 15 "$origin/admin/login/" -o /dev/null
curl -fsS --max-time 15 "$origin/static/content/admin-course-media.js" -o "$work/admin.js"
cmp "$BACKEND_CHECKOUT/backend/content/static/content/admin-course-media.js" "$work/admin.js"
curl -fsS --max-time 15 "$origin/header-navigation.js" -o "$work/header.js"
cmp "$FRONTEND_CHECKOUT/frontend/public/header-navigation.js" "$work/header.js"
echo "The staging media release is healthy at ${next##*/}. Both new image digests and public assets matched."
printf 'AWS staging task definition `%s` passed roll-out verification.\n' "${next##*/}" >> "$GITHUB_STEP_SUMMARY"
