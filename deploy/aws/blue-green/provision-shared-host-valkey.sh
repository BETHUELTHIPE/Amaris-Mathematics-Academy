#!/usr/bin/env bash
set -euo pipefail
umask 077
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=''
root=deploy/aws/blue-green
cluster=amaris-ecs-staging
service=amaris-web-staging-alb
prefix=/amaris/aws-staging/shared-valkey
[[ "$(aws sts get-caller-identity --query Account --output text)" == 110156539003 ]]
state="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e '.status=="ACTIVE" and .desiredCount==1 and .runningCount==1 and .pendingCount==0 and (.deployments|length)==1' <<< "$state" >/dev/null
target="$(jq -er '.loadBalancers[0].targetGroupArn' <<< "$state")"
aws elbv2 describe-target-health --target-group-arn "$target" --output json | jq -e 'any(.TargetHealthDescriptions[];.TargetHealth.State=="healthy")' >/dev/null
definition="$(aws ecs describe-task-definition --task-definition "$(jq -er .taskDefinition <<< "$state")" --query taskDefinition --output json)"
image="$(jq -er '.containerDefinitions[]|select(.name=="valkey")|.image' <<< "$definition")"
[[ "$image" =~ ^(docker\.io/)?valkey/valkey@sha256:[a-f0-9]{64}$ ]]
execution_role="$(jq -er '.executionRoleArn|split("/")|last' <<< "$definition")"
first="$(aws cloudformation describe-stack-resource --stack-name amaris-aws-staging --logical-resource-id StagingHost --query StackResourceDetail.PhysicalResourceId --output text)"
second="$(aws cloudformation describe-stack-resource --stack-name amaris-staging-ecs-second-host --logical-resource-id SecondHost --query StackResourceDetail.PhysicalResourceId --output text)"
[[ "$first" =~ ^i-[a-f0-9]+$ && "$second" =~ ^i-[a-f0-9]+$ && "$first" != "$second" ]]
instance="$(aws ec2 describe-instances --instance-ids "$second" --query 'Reservations[0].Instances[0]' --output json)"
jq -e '.State.Name=="running" and .InstanceType=="t4g.small" and .PublicIpAddress==null and (.SecurityGroups|length)==1' <<< "$instance" >/dev/null
ip="$(jq -er .PrivateIpAddress <<< "$instance")"
host_sg="$(jq -er '.SecurityGroups[0].GroupId' <<< "$instance")"
app_sg="$(jq -er '.networkConfiguration.awsvpcConfiguration.securityGroups|if length==1 then .[0] else error("unexpected application SGs") end' <<< "$state")"
[[ "$host_sg" != "$app_sg" && "$ip" =~ ^10\.86\.0\.[0-9]+$ ]]
subnet="$(jq -er .SubnetId <<< "$instance")"
jq -e --arg subnet "$subnet" '.networkConfiguration.awsvpcConfiguration.subnets|index($subnet)!=null' <<< "$state" >/dev/null
routes="$(aws ec2 describe-route-tables --filters "Name=association.subnet-id,Values=$subnet" --output json)"
jq -e '(.RouteTables|length)==1 and all(.RouteTables[].Routes[]; ((.GatewayId//"")|startswith("igw-")|not))' <<< "$routes" >/dev/null
profile="$(jq -er '.IamInstanceProfile.Arn|split("/")|last' <<< "$instance")"
host_role="$(aws iam get-instance-profile --instance-profile-name "$profile" --query 'InstanceProfile.Roles[0].RoleName' --output text)"
mapfile -t arns < <(aws ecs list-container-instances --cluster "$cluster" --status ACTIVE --query containerInstanceArns --output json | jq -r '.[]')
aws ecs describe-container-instances --cluster "$cluster" --container-instances "${arns[@]}" --output json | jq -e --arg id "$second" 'any(.containerInstances[];.ec2InstanceId==$id and .agentConnected and .runningTasksCount==0 and .pendingTasksCount==0)' >/dev/null
existing="$(aws ssm describe-parameters --parameter-filters "Key=Name,Option=BeginsWith,Values=$prefix/" --query 'Parameters[].Name' --output json)"
jq -e --arg p "$prefix/" 'all(.[]; .==($p+"host-password") or .==($p+"ca") or .==($p+"cache") or .==($p+"public-cache") or .==($p+"broker") or .==($p+"result"))' <<< "$existing" >/dev/null
if jq -e --arg p "$prefix/cache" 'index($p)!=null' <<< "$existing" >/dev/null && ! jq -e --arg p "$prefix/host-password" 'index($p)!=null' <<< "$existing" >/dev/null; then
  echo 'Existing cache configured elsewhere; refusing.' >&2; exit 1
fi
aws cloudformation deploy --stack-name amaris-staging-shared-host-valkey-access --template-file "$root/shared-host-valkey-access.yml" --capabilities CAPABILITY_NAMED_IAM --parameter-overrides "HostSecurityGroup=$host_sg" "ApplicationSecurityGroup=$app_sg" "HostRoleName=$host_role" "ExecutionRoleName=$execution_role" --no-fail-on-empty-changeset
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"; unset password' EXIT
put_once() {
  local name="$1" type="$2" value="$3" previous
  if jq -e --arg n "$name" 'index($n)!=null' <<< "$existing" >/dev/null; then
    previous="$(aws ssm get-parameter --name "$name" --with-decryption --query Parameter.Value --output text)"
    [[ "$previous" == "$value" ]] || { echo 'Existing parameter differs; refusing to rotate.' >&2; return 1; }
  else
    jq -n --arg name "$name" --arg type "$type" --arg value "$value" '{Name:$name,Value:$value,Type:$type,Tier:"Standard"}' > "$tmp/parameter.json"
    aws ssm put-parameter --cli-input-json "file://$tmp/parameter.json" >/dev/null
    rm "$tmp/parameter.json"
  fi
}
if ! jq -e --arg p "$prefix/host-password" 'index($p)!=null' <<< "$existing" >/dev/null; then
  put_once "$prefix/host-password" SecureString "$(openssl rand -hex 32)"
fi
{ printf '#!/usr/bin/env bash\nprivate_ip=%q\nimage=%q\n' "$ip" "$image"; cat "$root/install-shared-host-valkey.sh"; } > "$tmp/install.sh"
bash deploy/aws/ecs/run-on-host.sh "$second" "$tmp/install.sh" > "$tmp/ca.crt"
openssl x509 -in "$tmp/ca.crt" -noout >/dev/null
password="$(aws ssm get-parameter --name "$prefix/host-password" --with-decryption --query Parameter.Value --output text)"
[[ "$password" =~ ^[0-9a-f]{64}$ ]]
put_once "$prefix/ca" String "$(cat "$tmp/ca.crt")"
for pair in cache:0 public-cache:1 broker:2 result:3; do
  put_once "$prefix/${pair%:*}" SecureString "rediss://:$password@$ip:6379/${pair#*:}?ssl_cert_reqs=required&ssl_ca_certs=%2Ftmp%2Famaris-shared-valkey-ca.pem&ssl_check_hostname=true"
done
unset password
bash deploy/aws/ecs/run-on-host.sh "$first" "$root/probe-shared-host-valkey.sh" "$ip"
curl -fSs --max-time 15 https://16.171.164.5/health/ready/ | jq -e '.status=="ready"' >/dev/null
latest="$(aws ecs describe-services --cluster "$cluster" --services "$service" --query 'services[0]' --output json)"
jq -e --argjson old "$state" '.taskDefinition==$old.taskDefinition and .desiredCount==1 and .runningCount==1' <<< "$latest" >/dev/null
echo 'Shared host Valkey and old queue inventory verified. Existing web service unchanged. No new EC2, ElastiCache, EBS or load balancer created.'
