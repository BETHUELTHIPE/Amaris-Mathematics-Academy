#!/usr/bin/env bash
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
cluster=amaris-ecs-staging
service=amaris-web-staging-stateless
jobs=amaris-staging-singleton-jobs
root=deploy/aws/blue-green
runner=deploy/aws/ecs/run-on-host.sh
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount==2 and .runningCount==2 and .pendingCount==0 and (.deployments|length)==1 and .deployments[0].rolloutState=="COMPLETED"' <<< "$state" >/dev/null
target="$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$state")"
[[ "$target" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:targetgroup/amaris-staging-stateless/* ]]
aws elbv2 describe-target-health --target-group-arn "$target" --output json | jq -e '[.TargetHealthDescriptions[]|select(.TargetHealth.State=="healthy")]|length==2' >/dev/null
aws ecs describe-services --cluster "$cluster" --services amaris-web-staging-alb "$jobs" --output json | jq -e '(.services|length)==2 and all(.services[];.desiredCount==0 and .runningCount==0 and .pendingCount==0)' >/dev/null
legacy="$(aws ecs describe-task-definition --task-definition amaris-ecs-staging-alb-web:3 --query taskDefinition --output json)"
image="$(jq -er '.containerDefinitions[]|select(.name=="valkey")|.image' <<< "$legacy")"
[[ "$image" =~ ^(docker\.io/)?valkey/valkey@sha256:[a-f0-9]{64}$ ]]
digest="${image##*:}"
first="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost --query StackResourceDetail.PhysicalResourceId --output text)"
second="$(aws cloudformation describe-stack-resource --stack-name amaris-staging-ecs-second-host --logical-resource-id SecondHost --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$first" =~ ^i-[a-f0-9]+$ && "$second" =~ ^i-[a-f0-9]+$ && "$first" != "$second" ]]
ip="$(aws ec2 describe-instances --instance-ids "$second" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)"
[[ "$ip" =~ ^10\.86\.0\.[0-9]+$ ]]
job="$(aws ecs describe-services --cluster "$cluster" --services "$jobs" --query 'services[0]' --output json)"
jq -e --arg first "$first" '.status=="ACTIVE" and .deploymentConfiguration.maximumPercent==100 and .deploymentConfiguration.minimumHealthyPercent==0 and .placementConstraints==[{type:"memberOf",expression:("ec2InstanceId in [\u0027"+$first+"\u0027]")}]' <<< "$job" >/dev/null
definition="$(aws ecs describe-task-definition --task-definition "$(jq -er .taskDefinition <<< "$job")" --query taskDefinition --output json)"
jq -e '([.containerDefinitions[].name]|sort)==["celery-beat","celery-worker"] and (.volumes|length)==0 and all(.containerDefinitions[];.essential and (.mountPoints|length)==0 and any(.secrets[];.name=="AMARIS_SHARED_VALKEY_CA") and any(.secrets[];.name=="AMARIS_SHARED_CELERY_BROKER_URL"))' <<< "$definition" >/dev/null
mapfile -t hosts < <(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output json | jq -r '.[]')
aws ecs describe-container-instances --cluster "$cluster" --container-instances "${hosts[@]}" --output json | jq -e --arg first "$first" 'any(.containerInstances[];.ec2InstanceId==$first and .agentConnected and .runningTasksCount==1 and any(.remainingResources[];.name=="MEMORY" and .integerValue>=288) and any(.remainingResources[];.name=="CPU" and .integerValue>=96))' >/dev/null
aws ec2 describe-instances --instance-ids "$first" --output json | jq -e '.Reservations[0].Instances[0]|(.NetworkInterfaces|length)<3' >/dev/null
bash "$runner" "$first" "$root/reconcile-deadletter.sh" "$digest" "$ip"
echo 'Queue reconciliation complete. Activating singleton worker and scheduler.'
aws ecs update-service --cluster "$cluster" --service "$jobs" --desired-count 1 --query service.serviceName --output text
aws ecs wait services-stable --cluster "$cluster" --services "$jobs"
jobtask="$(aws ecs list-tasks --cluster "$cluster" --service-name "$jobs" --desired-status RUNNING --query 'taskArns[0]' --output text)"
[[ "$jobtask" =~ /[a-f0-9]{32}$ ]]
for _ in {1..20}; do
  detail="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$jobtask" --query 'tasks[0]' --output json)"
  if jq -e '.lastStatus=="RUNNING" and .healthStatus=="HEALTHY" and all(.containers[];.healthStatus=="HEALTHY")' <<< "$detail" >/dev/null; then break; fi
  sleep 5
done
jq -e '.lastStatus=="RUNNING" and .healthStatus=="HEALTHY" and all(.containers[];.healthStatus=="HEALTHY")' <<< "$detail" >/dev/null
bash "$runner" "$first" "$root/verify-shared-celery-jobs.sh" "$(basename "$jobtask")"
aws ecs describe-services --cluster "$cluster" --services "$jobs" "$service" --output json | jq -e 'any(.services[];.serviceName=="amaris-staging-singleton-jobs" and .desiredCount==1 and .runningCount==1 and .pendingCount==0 and (.deployments|length)==1) and any(.services[];.serviceName=="amaris-web-staging-stateless" and .runningCount==2 and .pendingCount==0)' >/dev/null
aws elbv2 describe-target-health --target-group-arn "$target" --output json | jq -e '[.TargetHealthDescriptions[]|select(.TargetHealth.State=="healthy")]|length==2' >/dev/null
curl -fSs --max-time 15 https://16.171.164.5/health/ready/ | jq -e '.status=="ready"' >/dev/null
echo 'PASS: singleton Celery worker and Beat running, all three queue probes passed, two web targets healthy.'
