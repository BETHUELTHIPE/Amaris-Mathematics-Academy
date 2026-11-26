#!/usr/bin/env bash
set -euo pipefail
umask 077
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
cluster=amaris-ecs-staging
service=amaris-web-staging-stateless
stack=amaris-staging-monitoring
topic=arn:aws:sns:eu-north-1:110156539003:amaris-staging-cloudwatch-alarms
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount==2 and .runningCount==2 and .pendingCount==0 and (.deployments|length)==1 and .deployments[0].rolloutState=="COMPLETED"' <<< "$state" >/dev/null
target="$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$state")"
[[ "$target" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:targetgroup/amaris-staging-stateless/* ]]
aws elbv2 describe-target-health --target-group-arn "$target" --output json | jq -e '[.TargetHealthDescriptions[]|select(.TargetHealth.State=="healthy")]|length==2' >/dev/null
alb="$(aws elbv2 describe-target-groups --target-group-arns "$target" --query 'TargetGroups[0].LoadBalancerArns[0]' --output text)"
[[ "$alb" == arn:aws:elasticloadbalancing:eu-north-1:110156539003:loadbalancer/app/amaris-staging-alb/* ]]
groupname="${target#*:targetgroup/}"
groupname="targetgroup/$groupname"
lbname="${alb#*loadbalancer/}"
# Use previous template and previous values to preserve the SNS recipient and
# all seven existing alarms. Do not reveal the NoEcho parameter.
metadata="$(aws cloudformation describe-stacks --stack-name "$stack" --output json)"
jq -e '.Stacks[0].StackStatus|test("^(CREATE|UPDATE)_COMPLETE$")' <<< "$metadata" >/dev/null
jq -e '([.Stacks[0].Parameters[].ParameterKey]|sort)==(["OperatorEmail","ClusterName","ServiceName","LoadBalancerFullName","ActiveTargetGroupFullName"]|sort)' <<< "$metadata" >/dev/null
if ! jq -e --arg s "$service" --arg tg "$groupname" 'any(.Stacks[0].Parameters[];.ParameterKey=="ServiceName" and .ParameterValue==$s) and any(.Stacks[0].Parameters[];.ParameterKey=="ActiveTargetGroupFullName" and .ParameterValue==$tg)' <<< "$metadata" >/dev/null; then
  aws cloudformation update-stack --stack-name "$stack" --use-previous-template --parameters \
    ParameterKey=OperatorEmail,UsePreviousValue=true ParameterKey=ClusterName,UsePreviousValue=true \
    "ParameterKey=ServiceName,ParameterValue=$service" "ParameterKey=LoadBalancerFullName,ParameterValue=$lbname" \
    "ParameterKey=ActiveTargetGroupFullName,ParameterValue=$groupname" --query StackId --output text >/dev/null
  aws cloudformation wait stack-update-complete --stack-name "$stack"
fi
allalarms=(amaris-staging-ecs-cpu-high amaris-staging-ecs-memory-high amaris-staging-no-healthy-targets amaris-staging-unhealthy-targets amaris-staging-alb-5xx amaris-staging-target-5xx amaris-staging-slow-responses)
alarms="$(aws cloudwatch describe-alarms --alarm-names "${allalarms[@]}" --output json)"
jq -e --arg topic "$topic" --arg service "$service" --arg cluster "$cluster" --arg tg "$groupname" --arg lb "$lbname" '
  (.MetricAlarms|length)==7 and all(.MetricAlarms[];.ActionsEnabled and (.AlarmActions|index($topic))!=null and
    (if .Namespace=="AWS/ECS" then (any(.Dimensions[];.Name=="ServiceName" and .Value==$service) and any(.Dimensions[];.Name=="ClusterName" and .Value==$cluster))
    elif (.MetricName=="HealthyHostCount" or .MetricName=="UnHealthyHostCount") then any(.Dimensions[];.Name=="TargetGroup" and .Value==$tg) and any(.Dimensions[];.Name=="LoadBalancer" and .Value==$lb)
    else .Dimensions==[{"Name":"LoadBalancer","Value":$lb}] end))
' <<< "$alarms" >/dev/null
jq '[.MetricAlarms[]|{name:.AlarmName,state:.StateValue,metric:.MetricName,dimensions:.Dimensions}]' <<< "$alarms"
aws sns list-subscriptions-by-topic --topic-arn "$topic" --output json | jq -e 'any(.Subscriptions[];.Protocol=="email" and (.SubscriptionArn|startswith("arn:aws:sns:")))' >/dev/null
echo 'PASS: seven monitoring alarms now reference the recovered ECS service and its ALB target group; confirmed SNS subscription preserved.'
# Only arm automatic rolling rollback when all three rollback alarms are OK.
names=(amaris-staging-alb-5xx amaris-staging-target-5xx amaris-staging-slow-responses)
alarms="$(aws cloudwatch describe-alarms --alarm-names "${names[@]}" --output json)"
if ! jq -e '(.MetricAlarms|length)==3 and all(.MetricAlarms[];.StateValue=="OK")' <<< "$alarms" >/dev/null; then
  echo 'BLOCKED: rollback alarms not all OK; leave deployment strategy unchanged.'
  exit 1
fi
latest="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e --argjson old "$state" '.taskDefinition==$old.taskDefinition and .desiredCount==2 and .runningCount==2 and .pendingCount==0 and (.deployments|length)==1 and .deployments[0].rolloutState=="COMPLETED"' <<< "$latest" >/dev/null
cfg='{"maximumPercent":100,"minimumHealthyPercent":50,"deploymentCircuitBreaker":{"enable":true,"rollback":true},"alarms":{"alarmNames":["amaris-staging-alb-5xx","amaris-staging-target-5xx","amaris-staging-slow-responses"],"enable":true,"rollback":true}}'
aws ecs update-service --cluster "$cluster" --service "$service" --deployment-configuration "$cfg" --query service.serviceName --output text
aws ecs describe-services --cluster "$cluster" --services "$service" --output json | jq -e --arg rev "$(jq -er .taskDefinition <<< "$state")" '.services[0]|.taskDefinition==$rev and .deploymentConfiguration.deploymentCircuitBreaker.rollback and .deploymentConfiguration.alarms.enable and .deploymentConfiguration.alarms.rollback and (.deploymentConfiguration.alarms.alarmNames|length)==3' >/dev/null
echo 'PASS: CloudWatch-triggered rolling rollback is configured on recovered staging service. No forced failure or actual rollback test was executed; native blue-green remains blocked on overlap capacity.'
