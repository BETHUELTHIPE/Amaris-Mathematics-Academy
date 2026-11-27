"""Prepare the narrow ECS secret read grant and audit native blue-green capacity.
No task registration, deployment, provisioning, traffic change or payment.
"""
import json
import re
import boto3
from botocore.exceptions import ClientError

ACCOUNT = "110156539003"
REGION = "eu-north-1"
CLUSTER = "amaris-ecs-staging"
PARAMETER = "/amaris/aws-staging/paystack/test-secret-key"
ARN = f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter{PARAMETER}"
POLICY = "AmarisStagingPaystackTestParameterRead"
REGISTRY = "amaris-staging-frontend"
DIGESTS = [
    "sha256:bc67977a14b7f91bc5e095715d413367e84595666c96ba41e237e1820df88d30",
    "sha256:6a90ef51552b39254b1945d8c3ff8ead5a8889da671122b7184558d56bb586c0",
]
session = boto3.Session(region_name=REGION)
assert session.client("sts").get_caller_identity()["Account"] == ACCOUNT
ecs, ec2, iam, cw, elb, ssm, ecr = [session.client(n) for n in ("ecs","ec2","iam","cloudwatch","elbv2","ssm","ecr")]
result = ecr.describe_images(repositoryName=REGISTRY, imageIds=[{"imageDigest": d} for d in DIGESTS])
assert {d["imageDigest"] for d in result["imageDetails"]} == set(DIGESTS)
assert ssm.get_parameter(Name=PARAMETER,WithDecryption=False)["Parameter"]["Type"] == "SecureString"
services = ecs.describe_services(cluster=CLUSTER,services=["amaris-web-staging-stateless","amaris-staging-singleton-jobs"])["services"]
assert len(services)==2
roles = set()
for svc in services:
    assert svc["status"]=="ACTIVE" and svc["runningCount"]==svc["desiredCount"] and svc["pendingCount"]==0 and len(svc["deployments"])==1
    task=ecs.describe_task_definition(taskDefinition=svc["taskDefinition"])["taskDefinition"]
    role=task["executionRoleArn"]
    assert re.fullmatch(rf"arn:aws:iam::{ACCOUNT}:role/amaris-[A-Za-z0-9+=,.@_-]+",role) and "staging" in role.lower()
    roles.add(role.rsplit("/",1)[-1])
    print("Service",svc["serviceName"],"revision",task["revision"],"running",svc["runningCount"])
    for c in task["containerDefinitions"]:
        print("Container",c["name"],"image pinned", "@sha256:" in c["image"])
web=next(s for s in services if s["serviceName"]=="amaris-web-staging-stateless")
assert web["runningCount"]==2
assert next(s for s in services if s["serviceName"]=="amaris-staging-singleton-jobs")["runningCount"]==1
doc={"Version":"2012-10-17","Statement":[{"Sid":"ReadOnlyStagingPaystackTestKey","Effect":"Allow","Action":"ssm:GetParameters","Resource":ARN}]}
for role in sorted(roles):
    try:
        old=iam.get_role_policy(RoleName=role,PolicyName=POLICY)["PolicyDocument"]
    except iam.exceptions.NoSuchEntityException:
        iam.put_role_policy(RoleName=role,PolicyName=POLICY,PolicyDocument=json.dumps(doc))
        old=iam.get_role_policy(RoleName=role,PolicyName=POLICY)["PolicyDocument"]
    assert old==doc, "Unexpected existing policy; no replacement"
    print("PASS: exact staging-only SSM read grant for ECS execution role",role)
cfg=web["deploymentConfiguration"]
alarms=cfg.get("alarms",{})
names=alarms.get("alarmNames",[])
actual=cw.describe_alarms(AlarmNames=names)["MetricAlarms"] if names else []
assert len(names)>=3 and len(actual)==len(names) and all(a["StateValue"]=="OK" and a["ActionsEnabled"] for a in actual)
assert alarms.get("enable") and alarms.get("rollback")
print("PASS: existing deployment alarm rollback enabled and healthy")
for lb in web["loadBalancers"]:
    targets=elb.describe_target_health(TargetGroupArn=lb["targetGroupArn"])["TargetHealthDescriptions"]
    assert sum(t["TargetHealth"]["State"]=="healthy" for t in targets)==2
print("PASS: two existing healthy ALB targets")
# Read only actual ECS/ENI placement capacity. Do not infer available trunk slots.
td=ecs.describe_task_definition(taskDefinition=web["taskDefinition"])["taskDefinition"]
def resource(c,n):
    return next((r.get("integerValue",0) for r in c.get("remainingResources",[]) if r["name"]==n),0)
cpu=int(td.get("cpu") or sum(c.get("cpu",0) for c in td["containerDefinitions"]))
mem=int(td.get("memory") or sum(c.get("memoryReservation",c.get("memory",0)) for c in td["containerDefinitions"]))
assert cpu>0 and mem>0
ids=ecs.list_container_instances(cluster=CLUSTER,status="ACTIVE")["containerInstanceArns"]
assert ids
hosts=ecs.describe_container_instances(cluster=CLUSTER,containerInstances=ids)["containerInstances"]
spare=0
for h in hosts:
    instance=ec2.describe_instances(InstanceIds=[h["ec2InstanceId"]])["Reservations"][0]["Instances"][0]
    typ=instance["InstanceType"]
    limits=ec2.describe_instance_types(InstanceTypes=[typ])["InstanceTypes"][0]["NetworkInfo"]
    trunk=any(a["name"]=="ecs.awsvpc-trunk-id" and a.get("value","").startswith("eni-") for a in h["attributes"])
    eni=resource(h,"ENI") if trunk else max(0,limits["MaximumNetworkInterfaces"]-len(instance["NetworkInterfaces"]))
    slots=min(resource(h,"CPU")//cpu,resource(h,"MEMORY")//mem,eni)
    if not h.get("agentConnected") or h.get("status")!="ACTIVE":
        slots=0
    spare+=slots
    print("Capacity",typ,"trunk",trunk,"conservative spare placements",slots)
print("Current deployment strategy:",cfg.get("strategy","ROLLING"),"spare placements:",spare)
if spare < 2:
    raise SystemExit("BLOCKED: not enough verified spare placement capacity for two simultaneous green tasks")
print("PASS: conservative spare placement calculation supports two additional web tasks; actual green launch and rollback drill still required.")
