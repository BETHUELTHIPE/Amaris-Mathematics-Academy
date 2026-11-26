#!/usr/bin/env bash
set -euo pipefail
umask 077
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
root=deploy/aws/blue-green
runner=deploy/aws/ecs/run-on-host.sh
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
jobs=amaris-staging-singleton-jobs
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount==1 and .runningCount==1 and .pendingCount==0 and (.deployments|length)==1 and (.placementConstraints|length)==1 and (.loadBalancers|length)==1' <<< "$state" >/dev/null
old="$(jq -er .taskDefinition <<< "$state")"
target="$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$state")"
first="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost --query StackResourceDetail.PhysicalResourceId --output text)"
second="$(aws cloudformation describe-stack-resource --stack-name amaris-staging-ecs-second-host --logical-resource-id SecondHost --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$first" =~ ^i-[a-f0-9]+$ && "$second" =~ ^i-[a-f0-9]+$ && "$first" != "$second" ]]
ip="$(aws ec2 describe-instances --instance-ids "$second" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)"
[[ "$ip" =~ ^10\.86\.0\.[0-9]+$ ]]
task="$(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --desired-status RUNNING --query 'taskArns[0]' --output text)"
[[ "$task" =~ /[a-f0-9]{32}$ ]]
oldid="$(basename "$task")"
target_ok() { aws elbv2 describe-target-health --target-group-arn "$target" --output json | jq -e --argjson n "$1" '[.TargetHealthDescriptions[]|select(.TargetHealth.State=="healthy")]|length==$n' >/dev/null; }
target_ok 1
# Refuse concurrent deployments, existing separate jobs, or missing shared configuration.
jobs_before="$(aws ecs describe-services --cluster "$cluster" --services "$jobs" --output json)"
jq -e 'all(.services[];.status=="INACTIVE" or (.status=="ACTIVE" and .desiredCount==0 and .runningCount==0 and .pendingCount==0))' <<< "$jobs_before" >/dev/null
params="$(aws ssm describe-parameters --parameter-filters Key=Name,Option=BeginsWith,Values=/amaris/aws-staging/shared-valkey/ --query 'Parameters[].Name' --output json)"
for key in cache public-cache broker result ca host-password; do jq -e --arg p "/amaris/aws-staging/shared-valkey/$key" 'index($p)!=null' <<< "$params" >/dev/null; done
mapfile -t hosts < <(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output json | jq -r '.[]')
aws ecs describe-container-instances --cluster "$cluster" --container-instances "${hosts[@]}" --output json | jq -e --arg a "$first" --arg b "$second" '
  [.containerInstances[]|select(.agentConnected)]|length==2 and
  any(.[];.ec2InstanceId==$a and .runningTasksCount==1 and any(.registeredResources[];.name=="MEMORY" and .integerValue>=1500)) and
  any(.[];.ec2InstanceId==$b and .runningTasksCount==0 and any(.remainingResources[];.name=="MEMORY" and .integerValue>=1500))' >/dev/null
tmp="$(mktemp -d)"
phase=before
maintenance=0
old_placement="$(jq -c '.placementConstraints' <<< "$state")"
old_deploy="$(jq -c '.deploymentConfiguration|{maximumPercent,minimumHealthyPercent,deploymentCircuitBreaker}|with_entries(select(.value!=null))' <<< "$state")"
network="$(jq -c .networkConfiguration <<< "$state")"
rollback() {
  rc=$?
  trap - EXIT
  if [[ "$rc" != 0 && "$maintenance" == 1 ]]; then
    if [[ "$phase" == before || "$phase" == copied ]]; then
      echo 'Before consumer activation: restoring original source service and gateway.' >&2
      bash "$runner" "$first" "$root/unpause-old-broker.sh" "$oldid" || true
      current="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0].taskDefinition' --output text || true)"
      if [[ "$current" != "$old" ]]; then
        aws ecs update-service --cluster "$cluster" --service "$service" --desired-count 0 --query service.serviceName --output text >/dev/null || true
        if ! aws ecs wait services-stable --cluster "$cluster" --services "$service"; then
          echo 'Could not stop replacement web tasks safely; maintenance retained.' >&2
          rm -rf "$tmp"; exit "$rc"
        fi
      fi
      aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$old" --desired-count 1 --placement-constraints "$old_placement" --deployment-configuration "$old_deploy" --query service.serviceName --output text >/dev/null || true
      if aws ecs wait services-stable --cluster "$cluster" --services "$service" && target_ok 1; then
        bash "$runner" "$first" "$root/cutover-gateway.sh" off || true
      else echo 'Old service recovery not healthy; gateway remains in maintenance.' >&2; fi
    else
      echo 'Shared broker may contain processed jobs. Do not restore the stale local broker.' >&2
      if target_ok 2; then
        bash "$runner" "$first" "$root/cutover-gateway.sh" off || true
        echo 'Healthy stateless web targets retained; Celery acceptance failed and requires repair using shared state.' >&2
      else
        echo 'Replacement web targets not healthy; maintenance retained.' >&2
      fi
    fi
  fi
  rm -rf "$tmp"
  exit "$rc"
}
trap rollback EXIT
aws ecs describe-task-definition --task-definition "$old" --query taskDefinition --output json | python3 "$root/render-multitask.py" --host-valkey > "$tmp/split.json"
jq '.web' "$tmp/split.json" > "$tmp/web.json"
jq '.jobs' "$tmp/split.json" > "$tmp/jobs.json"
webrev="$(aws ecs register-task-definition --cli-input-json "file://$tmp/web.json" --query taskDefinition.taskDefinitionArn --output text)"
jobsrev="$(aws ecs register-task-definition --cli-input-json "file://$tmp/jobs.json" --query taskDefinition.taskDefinitionArn --output text)"
[[ "$webrev" == arn:aws:ecs:eu-north-1:110156539003:task-definition/amaris-ecs-staging-alb-web:* && "$jobsrev" == arn:aws:ecs:eu-north-1:110156539003:task-definition/amaris-ecs-staging-singleton-jobs:* ]]
# Establish an empty service first; it cannot consume jobs until explicitly activated.
pin="$(jq -nc --arg x "ec2InstanceId in ['$first']" '[{type:"memberOf",expression:$x}]')"
if jq -e 'any(.services[];.status=="ACTIVE")' <<< "$jobs_before" >/dev/null; then
  aws ecs update-service --cluster "$cluster" --service "$jobs" --task-definition "$jobsrev" --desired-count 0 --placement-constraints "$pin" --deployment-configuration maximumPercent=100,minimumHealthyPercent=0 --query service.serviceName --output text
else
  aws ecs create-service --cluster "$cluster" --service-name "$jobs" --task-definition "$jobsrev" --desired-count 0 --launch-type EC2 --network-configuration "$network" --placement-constraints "$pin" --deployment-configuration maximumPercent=100,minimumHealthyPercent=0 --query service.serviceName --output text
fi
resource="service/$cluster/$service"
aws application-autoscaling register-scalable-target --service-namespace ecs --scalable-dimension ecs:service:DesiredCount --resource-id "$resource" --min-capacity 1 --max-capacity 2 --suspended-state DynamicScalingInSuspended=true,DynamicScalingOutSuspended=true,ScheduledScalingSuspended=true >/dev/null
maintenance=1
bash "$runner" "$first" "$root/cutover-gateway.sh" on
sleep 8
{ printf '#!/usr/bin/env bash\nmigration_code=$(cat <<'\''AMARIS_MIGRATION_PY'\''\n'; cat "$root/migrate-valkey-data.py"; printf '\nAMARIS_MIGRATION_PY\n)\n'; cat "$root/freeze-copy-valkey.sh"; } > "$tmp/migrate.sh"
bash "$runner" "$first" "$tmp/migrate.sh" "$oldid" "$ip"
phase=copied
aws ecs update-service --cluster "$cluster" --service "$service" --desired-count 0 --query service.serviceName --output text
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task"
aws ecs wait services-stable --cluster "$cluster" --services "$service"
# Preserve old disk and never start another local-broker task after enabling shared consumers.
aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$webrev" --desired-count 2 --placement-constraints '[{"type":"distinctInstance"}]' --deployment-configuration 'maximumPercent=150,minimumHealthyPercent=100,deploymentCircuitBreaker={enable=true,rollback=false}' --query service.serviceName --output text
aws ecs wait services-stable --cluster "$cluster" --services "$service"
target_ok 2
mapfile -t webtasks < <(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --desired-status RUNNING --query taskArns --output json | jq -r '.[]')
[[ "${#webtasks[@]}" == 2 ]]
for item in "${webtasks[@]}"; do
  detail="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$item" --query 'tasks[0]' --output json)"
  jq -e --arg rev "$webrev" '.taskDefinitionArn==$rev and .lastStatus=="RUNNING" and .healthStatus=="HEALTHY"' <<< "$detail" >/dev/null
  host="$(aws ecs describe-container-instances --cluster "$cluster" --container-instances "$(jq -er .containerInstanceArn <<< "$detail")" --query 'containerInstances[0].ec2InstanceId' --output text)"
  bash "$runner" "$host" deploy/aws/diagnostics/verify-web-stack.sh task "$(basename "$item")"
done
# Once consumers start, a rollback may only use the shared broker.
phase=consumers
aws ecs update-service --cluster "$cluster" --service "$jobs" --desired-count 1 --query service.serviceName --output text
aws ecs wait services-stable --cluster "$cluster" --services "$jobs"
jobtask="$(aws ecs list-tasks --cluster "$cluster" --service-name "$jobs" --desired-status RUNNING --query 'taskArns[0]' --output text)"
[[ "$jobtask" =~ /[a-f0-9]{32}$ ]]
for _ in {1..15}; do
  detail="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$jobtask" --query 'tasks[0]' --output json)"
  if jq -e --arg rev "$jobsrev" '.taskDefinitionArn==$rev and .healthStatus=="HEALTHY" and .lastStatus=="RUNNING"' <<< "$detail" >/dev/null; then break; fi
  sleep 5
done
jq -e '.healthStatus=="HEALTHY"' <<< "$detail" >/dev/null
bash "$runner" "$first" "$root/verify-shared-celery-jobs.sh" "$(basename "$jobtask")"
target_ok 2
bash "$runner" "$first" "$root/cutover-gateway.sh" off
maintenance=0
curl -fSs --max-time 15 https://16.171.164.5/health/ready/ | jq -e '.status=="ready"' >/dev/null
curl -fSs --max-time 15 https://16.171.164.5/api/v1/bootstrap/ | jq -e 'has("settings")' >/dev/null
echo 'CUTOVER PASS: two stateless web tasks, one shared-broker Celery worker/Beat task, public staging healthy. Scaling remains paused at 1–2 until capacity verified.'
