"""Register unused, immutable staging candidates with exact payment secret injection."""
import copy
import json
import re
import boto3
from urllib.request import urlopen
ACCOUNT="110156539003"
REGION="eu-north-1"
CLUSTER="amaris-ecs-staging"
BASE="cfdb105761836c7730fec52ada54c58c624206db"
SHA="164838a3143c22cc7b60ab669e1f0c7dca616a0f"
FRONT="887ebf099bd490a7db8c0554bb20353feb3ffb89"
REGISTRY=f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/amaris-staging-frontend"
BACKEND=REGISTRY+"@sha256:bc67977a14b7f91bc5e095715d413367e84595666c96ba41e237e1820df88d30"
FRONTEND=REGISTRY+"@sha256:6a90ef51552b39254b1945d8c3ff8ead5a8889da671122b7184558d56bb586c0"
PARAMETER=f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/amaris/aws-staging/paystack/test-secret-key"
KEY="PAYSTACK_SECRET_KEY"
session=boto3.Session(region_name=REGION)
assert session.client("sts").get_caller_identity()["Account"]==ACCOUNT
ecs=session.client("ecs")
with urlopen("https://16.171.164.5/health/version/",timeout=15) as r:
    assert json.load(r)["git_sha"]==BASE
svcs=ecs.describe_services(cluster=CLUSTER,services=["amaris-web-staging-stateless","amaris-staging-singleton-jobs"])["services"]
assert len(svcs)==2
allowed={"family","taskRoleArn","executionRoleArn","networkMode","containerDefinitions","volumes","placementConstraints","requiresCompatibilities","cpu","memory","pidMode","ipcMode","proxyConfiguration","inferenceAccelerators","ephemeralStorage","runtimePlatform","enableFaultInjection"}
for svc in svcs:
    assert svc["status"]=="ACTIVE" and svc["pendingCount"]==0 and svc["runningCount"]==svc["desiredCount"] and len(svc["deployments"])==1
    task=ecs.describe_task_definition(taskDefinition=svc["taskDefinition"],include=["TAGS"])
    src=task["taskDefinition"]
    assert src["networkMode"]=="awsvpc" and not src.get("volumes") and src["runtimePlatform"]["cpuArchitecture"]=="ARM64"
    assert src["family"].startswith("amaris-ecs-staging")
    req={k:copy.deepcopy(v) for k,v in src.items() if k in allowed and v is not None}
    names={c["name"] for c in req["containerDefinitions"]}
    assert names in ({"backend","frontend","cms"},{"celery-worker","celery-beat"}), "Unexpected service topology"
    for c in req["containerDefinitions"]:
        name=c["name"]
        if name=="cms":
            continue
        assert c["image"].startswith(REGISTRY+"@sha256:") and not c.get("mountPoints")
        entry=c.get("entryPoint",[])
        assert len(entry)>=3 and entry[:2]==["/bin/sh","-ec"] and entry[2].count('exec "$@"')==1
        if name=="frontend":
            c["image"]=FRONTEND
            continue
        c["image"]=BACKEND
        assert any(x["name"]=="AMARIS_RUNTIME_ENV" for x in c.get("secrets",[]))
        # Preserve secret injected by ECS even if the existing runtime loader sets environment values.
        assert "amaris_paystack_test_key" not in entry[2]
        wrapper=re.sub(r"export RELEASE_GIT_SHA=[0-9a-f]{40}\n","",entry[2])
        wrapper='amaris_paystack_test_key="$PAYSTACK_SECRET_KEY"\n'+wrapper
        wrapper=wrapper.replace('exec "$@"','export PAYSTACK_SECRET_KEY="$amaris_paystack_test_key"\nunset amaris_paystack_test_key\nexport PAYSTACK_MODE=test\nexport PAYSTACK_ENABLED=false\nexport RELEASE_GIT_SHA='+SHA+'\nexec "$@"')
        entry[2]=wrapper
        c["environment"]=[x for x in c.get("environment",[]) if x["name"] not in {KEY,"PAYSTACK_MODE","PAYSTACK_ENABLED"}]+[{"name":"PAYSTACK_MODE","value":"test"},{"name":"PAYSTACK_ENABLED","value":"false"}]
        c["secrets"]=[x for x in c.get("secrets",[]) if x["name"] not in {KEY,"PAYSTACK_MODE","PAYSTACK_ENABLED"}]+[{"name":KEY,"valueFrom":PARAMETER}]
    tags=[x for x in task.get("tags",[]) if not x["key"].startswith("aws:") and x["key"]!="AmarisCandidate"]
    req["tags"]=tags+[{"key":"AmarisCandidate","value":"paystack-test-disabled"}]
    # The active service reference is unchanged; the new task revision is inert.
    out=ecs.register_task_definition(**req)["taskDefinition"]
    for c in out["containerDefinitions"]:
        if c["name"] in ("backend","celery-worker","celery-beat"):
            assert {"name":KEY,"valueFrom":PARAMETER} in c["secrets"]
            assert {"name":"PAYSTACK_ENABLED","value":"false"} in c["environment"]
    after=ecs.describe_services(cluster=CLUSTER,services=[svc["serviceName"]])["services"][0]
    assert after["taskDefinition"]==svc["taskDefinition"]
    print("PASS: inactive candidate",out["taskDefinitionArn"].rsplit("/",1)[-1],"with sandbox key and checkout disabled; active service unchanged.")
print("No migrations, traffic shifts, live-mode keys or payments.")
