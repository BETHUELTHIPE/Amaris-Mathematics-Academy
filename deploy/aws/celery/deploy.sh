#!/usr/bin/env bash
set -euo pipefail
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
instance="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$instance" =~ ^i-[a-f0-9]+$ ]]
state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e --arg host "ec2InstanceId in ['$instance']" '
  .status=="ACTIVE" and .desiredCount==1 and .runningCount==1 and .pendingCount==0
  and (.deployments|length)==1 and .deploymentController.type=="ECS"
  and .deploymentConfiguration.maximumPercent==100 and .deploymentConfiguration.minimumHealthyPercent==0
  and .placementConstraints==[{type:"memberOf",expression:$host}]
' <<< "$state" >/dev/null
old="$(jq -er .taskDefinition <<< "$state")"
definition="$(aws ecs describe-task-definition --task-definition "$old" --query taskDefinition --output json)"
{
  printf 'CELERY_STAGING_INSTANCE=%s\n' "$instance"
  printf 'CELERY_STAGING_PREVIOUS_REVISION=%s\n' "$old"
  printf 'CELERY_STAGING_TARGET=%s\n' "$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$state")"
} >> "$GITHUB_ENV"
if jq -e 'any(.containerDefinitions[];.name=="celery-worker" or .name=="celery-beat")' <<< "$definition" >/dev/null; then
  jq -e '[.containerDefinitions[].name]| index("celery-worker") != null and index("celery-beat") != null' <<< "$definition" >/dev/null
  printf 'CELERY_STAGING_REVISION=%s\n' "$old" >> "$GITHUB_ENV"
  exit 0
fi
binary="$(base64 -w0 deploy/aws/celery/staging_celery.py)"
host_script="$RUNNER_TEMP/amaris-install-celery.sh"
{
  printf '#!/usr/bin/env bash\nset -euo pipefail\n'
  printf 'install -d -m 0755 /opt/amaris-staging/celery\n'
  printf "printf '%%s' '%s' | base64 -d > /opt/amaris-staging/celery/staging_celery.py\n" "$binary"
  printf 'chmod 0644 /opt/amaris-staging/celery/staging_celery.py\n'
} > "$host_script"
bash deploy/aws/ecs/run-on-host.sh "$instance" "$host_script"
new_definition="$RUNNER_TEMP/amaris-ecs-with-celery.json"
python3 deploy/aws/celery/render-task.py <<< "$definition" > "$new_definition"
revision="$(aws ecs register-task-definition --cli-input-json "file://$new_definition" \
  --query taskDefinition.taskDefinitionArn --output text)"
[[ "$revision" == arn:aws:ecs:eu-north-1:110156539003:task-definition/amaris-ecs-staging-alb-web:* ]]
printf 'CELERY_STAGING_REVISION=%s\n' "$revision" >> "$GITHUB_ENV"
aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$revision" \
  --query 'service.[serviceName,taskDefinition]' --output text
