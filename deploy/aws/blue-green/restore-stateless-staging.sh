#!/usr/bin/env bash
set -euo pipefail
umask 077
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
cluster=amaris-ecs-staging
legacy=amaris-web-staging-alb
service=amaris-web-staging-stateless
jobs=amaris-staging-singleton-jobs
root=deploy/aws/blue-green
runner=deploy/aws/ecs/run-on-host.sh
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
old="$(aws ecs describe-services --cluster "$cluster" --services "$legacy" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount==0 and .runningCount==0 and .pendingCount==0 and (.loadBalancers|length)==1' <<< "$old" >/dev/null
job="$(aws ecs describe-services --cluster "$cluster" --services "$jobs" --query 'services[0]' --output json)"
jq -e '.desiredCount==0 and .runningCount==0 and .pendingCount==0' <<< "$job" >/dev/null
rev="$(jq -er .taskDefinition <<< "$old")"
def="$(aws ecs describe-task-definition --task-definition "$rev" --query taskDefinition --output json)"
jq -e '([.containerDefinitions[].name]|sort)==["backend","cms","frontend"] and (.volumes|length)==0 and all(.containerDefinitions[];(.mountPoints|length)==0) and any(.containerDefinitions[]|select(.name=="backend")|.secrets[];.name=="AMARIS_SHARED_VALKEY_CA")' <<< "$def" >/dev/null
first="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$first" =~ ^i-[a-f0-9]+$ ]]
oldtarget="$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$old")"
alb="$(aws elbv2 describe-load-balancers --names amaris-staging-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)"
[[ "$alb" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:loadbalancer/app/amaris-staging-alb/* ]]
vpc="$(aws elbv2 describe-load-balancers --load-balancer-arns "$alb" --query 'LoadBalancers[0].VpcId' --output text)"
listener="$(aws elbv2 describe-listeners --load-balancer-arn "$alb" --output json | jq -er '.Listeners[]|select(.Port==80)')"
listenerarn="$(jq -er .ListenerArn <<< "$listener")"
jq -e '.Protocol=="HTTP" and (.DefaultActions|length)==1 and .DefaultActions[0].Type=="forward"' <<< "$listener" >/dev/null
network="$(jq -c .networkConfiguration <<< "$old")"
aws application-autoscaling register-scalable-target --service-namespace ecs --scalable-dimension ecs:service:DesiredCount --resource-id "service/$cluster/$legacy" --min-capacity 0 --max-capacity 2 --suspended-state DynamicScalingInSuspended=true,DynamicScalingOutSuspended=true,ScheduledScalingSuspended=true >/dev/null
target="$(aws elbv2 describe-target-groups --names amaris-staging-stateless --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)"
if [[ -z "$target" || "$target" == None ]]; then
  target="$(aws elbv2 create-target-group --name amaris-staging-stateless --protocol HTTP --port 8080 --vpc-id "$vpc" --target-type ip --health-check-path /__alb/ready --health-check-interval-seconds 15 --health-check-timeout-seconds 5 --healthy-threshold-count 2 --unhealthy-threshold-count 3 --matcher HttpCode=200 --tags Key=Environment,Value=staging Key=Project,Value=Amaris --query 'TargetGroups[0].TargetGroupArn' --output text)"
fi
[[ "$target" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:targetgroup/amaris-staging-stateless/* ]]
aws elbv2 describe-target-groups --target-group-arns "$target" --output json | jq -e --arg v "$vpc" '.TargetGroups[0]|.VpcId==$v and .TargetType=="ip" and .Port==8080 and .HealthCheckPath=="/__alb/ready"' >/dev/null
aws elbv2 modify-target-group-attributes --target-group-arn "$target" --attributes Key=deregistration_delay.timeout_seconds,Value=30 >/dev/null
current="$(jq -r '.DefaultActions[0].TargetGroupArn // .DefaultActions[0].ForwardConfig.TargetGroups[0].TargetGroupArn' <<< "$listener")"
[[ "$current" == "$oldtarget" || "$current" == "$target" ]]
aws elbv2 modify-listener --listener-arn "$listenerarn" --default-actions "Type=forward,TargetGroupArn=$target" >/dev/null
existing="$(aws ecs describe-services --cluster "$cluster" --services "$service" --output json)"
if jq -e 'any(.services[];.status=="ACTIVE")' <<< "$existing" >/dev/null; then
  jq -e --arg t "$target" --arg r "$rev" '.services[0]|.taskDefinition==$r and .loadBalancers[0].targetGroupArn==$t' <<< "$existing" >/dev/null
else
  lb="$(jq -nc --arg target "$target" '[{targetGroupArn:$target,containerName:"cms",containerPort:8080}]')"
  aws ecs create-service --cluster "$cluster" --service-name "$service" --task-definition "$rev" --desired-count 2 --launch-type EC2 --network-configuration "$network" --load-balancers "$lb" --placement-constraints '[{"type":"distinctInstance"}]' --deployment-configuration '{"maximumPercent":100,"minimumHealthyPercent":50,"deploymentCircuitBreaker":{"enable":true,"rollback":false}}' --health-check-grace-period-seconds 180 --tags key=Environment,value=staging key=Project,value=Amaris --query service.serviceName --output text
fi
opened=0
for attempt in {1..48}; do
  state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
  targets="$(aws elbv2 describe-target-health --target-group-arn "$target" --output json)"
  healthy="$(jq '[.TargetHealthDescriptions[]|select(.TargetHealth.State=="healthy")]|length' <<< "$targets")"
  echo "Attempt $attempt: desired=$(jq .desiredCount <<< "$state") running=$(jq .runningCount <<< "$state") healthy=$healthy"
  if [[ "$healthy" -ge 1 && "$opened" == 0 ]]; then
    bash "$runner" "$first" "$root/cutover-gateway.sh" off
    opened=1
    curl -fSs --max-time 15 https://16.171.164.5/health/ready/ | jq -e '.status=="ready"' >/dev/null
    echo 'PUBLIC STAGING RESTORED via stateless ECS'
  fi
  if [[ "$healthy" == 2 ]] && jq -e '.desiredCount==2 and .runningCount==2 and .pendingCount==0 and (.deployments|length)==1 and .deployments[0].rolloutState=="COMPLETED"' <<< "$state" >/dev/null; then
    mapfile -t tasks < <(aws ecs list-tasks --cluster "$cluster" --service-name "$service" --desired-status RUNNING --query taskArns --output json | jq -r '.[]')
    [[ "${#tasks[@]}" == 2 ]]
    for task in "${tasks[@]}"; do
      detail="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query 'tasks[0]' --output json)"
      jq -e --arg r "$rev" '.taskDefinitionArn==$r and .healthStatus=="HEALTHY"' <<< "$detail" >/dev/null
      host="$(aws ecs describe-container-instances --cluster "$cluster" --container-instances "$(jq -er .containerInstanceArn <<< "$detail")" --query 'containerInstances[0].ec2InstanceId' --output text)"
      bash "$runner" "$host" deploy/aws/diagnostics/verify-web-stack.sh task "$(basename "$task")"
    done
    curl -fSs --max-time 15 https://16.171.164.5/api/v1/bootstrap/ | jq -e 'has("settings")' >/dev/null
    echo 'PASS: two healthy stateless ECS web tasks and public API. Celery remains intentionally stopped.'
    exit 0
  fi
  sleep 10
done
echo 'Two-target acceptance incomplete; any restored healthy website remains available. Inspect ECS events.' >&2
aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0].events[0:5].message' --output json
exit 1
