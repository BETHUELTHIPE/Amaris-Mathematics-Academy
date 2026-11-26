#!/usr/bin/env bash
set -euo pipefail
umask 077
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
root=deploy/aws/blue-green
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
before="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount==1 and .runningCount==1 and .pendingCount==0 and (.deployments|length)==1' <<< "$before" >/dev/null
prefix=/amaris/aws-staging/shared-valkey
params="$(aws ssm describe-parameters --parameter-filters "Key=Name,Option=BeginsWith,Values=$prefix/" --query 'Parameters[].{Name:Name,Type:Type}' --output json)"
for suffix in cache public-cache broker result; do
  jq -e --arg n "$prefix/$suffix" 'any(.[];.Name==$n and .Type=="SecureString")' <<< "$params" >/dev/null
done
jq -e --arg n "$prefix/ca" 'any(.[];.Name==$n and .Type=="String")' <<< "$params" >/dev/null
second="$(aws cloudformation describe-stack-resource --stack-name amaris-staging-ecs-second-host --logical-resource-id SecondHost --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$second" =~ ^i-[a-f0-9]+$ ]]
instance="$(aws ec2 describe-instances --instance-ids "$second" --query 'Reservations[0].Instances[0]' --output json)"
jq -e '.State.Name=="running" and .PublicIpAddress==null' <<< "$instance" >/dev/null
subnet="$(jq -er .SubnetId <<< "$instance")"
sg="$(jq -er '.networkConfiguration.awsvpcConfiguration.securityGroups|if length==1 then .[0] else error("unexpected SGs") end' <<< "$before")"
jq -e --arg s "$subnet" '.networkConfiguration.awsvpcConfiguration.subnets|index($s)!=null' <<< "$before" >/dev/null
mapfile -t ids < <(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output json | jq -r '.[]')
aws ecs describe-container-instances --cluster "$cluster" --container-instances "${ids[@]}" --output json | jq -e --arg id "$second" 'any(.containerInstances[];.ec2InstanceId==$id and .agentConnected and .runningTasksCount==0 and .pendingTasksCount==0 and any(.remainingResources[];.name=="MEMORY" and .integerValue>=1000))' >/dev/null
tmp="$(mktemp -d)"
task=''
revision=''
cleanup() {
  if [[ -n "$task" ]]; then
    aws ecs stop-task --cluster "$cluster" --task "$task" --reason 'Amaris isolated shared-Valkey canary cleanup' --query task.taskArn --output text >/dev/null 2>&1 || true
  fi
  if [[ -n "$revision" ]]; then
    aws ecs deregister-task-definition --task-definition "$revision" --query taskDefinition.taskDefinitionArn --output text >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT
aws ecs describe-task-definition --task-definition "$(jq -er .taskDefinition <<< "$before")" --query taskDefinition --output json |
  python3 "$root/render-multitask.py" --host-valkey > "$tmp/split.json"
jq --rawfile code "$root/check-shared-valkey-runtime.py" '.web | .family="amaris-staging-shared-valkey-canary" | del(.placementConstraints,.cpu,.memory) |
  .containerDefinitions=[.containerDefinitions[]|select(.name=="backend")|del(.healthCheck,.dependsOn,.restartPolicy,.portMappings)|.command=["python","-c",$code]]' "$tmp/split.json" > "$tmp/canary.json"
revision="$(aws ecs register-task-definition --cli-input-json "file://$tmp/canary.json" --query taskDefinition.taskDefinitionArn --output text)"
[[ "$revision" == arn:aws:ecs:eu-north-1:110156539003:task-definition/amaris-staging-shared-valkey-canary:* ]]
network="$(jq -nc --arg subnet "$subnet" --arg sg "$sg" '{awsvpcConfiguration:{subnets:[$subnet],securityGroups:[$sg],assignPublicIp:"DISABLED"}}')"
constraint="$(jq -nc --arg expression "ec2InstanceId in ['$second']" '[{type:"memberOf",expression:$expression}]')"
response="$(aws ecs run-task --cluster "$cluster" --task-definition "$revision" --launch-type EC2 --count 1 --network-configuration "$network" --placement-constraints "$constraint" --started-by amaris-shared-valkey-canary --output json)"
jq -e '(.failures|length)==0 and (.tasks|length)==1' <<< "$response" >/dev/null
task="$(jq -er '.tasks[0].taskArn' <<< "$response")"
for attempt in {1..48}; do
  detail="$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" --query 'tasks[0]' --output json)"
  if jq -e '.lastStatus=="STOPPED"' <<< "$detail" >/dev/null; then break; fi
  sleep 5
done
jq '{lastStatus,stopCode,containers:[.containers[]|{name,exitCode,lastStatus}]}' <<< "$detail"
jq -e '.lastStatus=="STOPPED" and .containers[0].exitCode==0' <<< "$detail" >/dev/null
after="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e --argjson old "$before" '.taskDefinition==$old.taskDefinition and .desiredCount==1 and .runningCount==1' <<< "$after" >/dev/null
echo 'Isolated ARM64 ECS canary passed actual Django cache and Celery TLS connection checks. No queue migration or live service change.'
