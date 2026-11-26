"""Read-only state inspection during cutover; no secret retrieval or service mutation."""
import json
import subprocess
import urllib.request
import urllib.error

cluster="amaris-ecs-staging"
services=("amaris-web-staging-alb","amaris-staging-singleton-jobs")
def aws(*args):
    return json.loads(subprocess.check_output(["aws",*args,"--output","json"],text=True))
def report(label, data):
    print(label+": "+json.dumps(data),flush=True)
assert aws("sts","get-caller-identity")["Account"]=="110156539003"
for svc in aws("ecs","describe-services","--cluster",cluster,"--services",*services)["services"]:
    name=svc["serviceName"]
    report("SERVICE "+name,{k:svc.get(k) for k in ("status","desiredCount","runningCount","pendingCount","taskDefinition","deploymentConfiguration","placementConstraints")})
    report("DEPLOYMENTS",[{k:d.get(k) for k in ("id","status","taskDefinition","desiredCount","runningCount","pendingCount","rolloutState","rolloutStateReason","failedTasks")} for d in svc["deployments"]])
    report("EVENTS",[{k:e.get(k) for k in ("createdAt","message")} for e in svc["events"][:8]])
    active=aws("ecs","list-tasks","--cluster",cluster,"--service-name",name,"--desired-status","RUNNING")["taskArns"]
    stopped=aws("ecs","list-tasks","--cluster",cluster,"--service-name",name,"--desired-status","STOPPED","--max-items","8")["taskArns"]
    for arn in active+stopped:
        t=aws("ecs","describe-tasks","--cluster",cluster,"--tasks",arn)["tasks"][0]
        report("TASK",{**{k:t.get(k) for k in ("taskArn","taskDefinitionArn","lastStatus","desiredStatus","healthStatus","stopCode","stoppedReason","containerInstanceArn","createdAt","stoppedAt")},"containers":[{k:c.get(k) for k in ("name","healthStatus","lastStatus","exitCode","reason")} for c in t["containers"]]})
    for lb in svc["loadBalancers"]:
        report("ALB",aws("elbv2","describe-target-health","--target-group-arn",lb["targetGroupArn"])["TargetHealthDescriptions"])
for path in ("/health/ready/","/health/dependencies/","/api/v1/bootstrap/"):
    try:
        with urllib.request.urlopen("https://16.171.164.5"+path,timeout=8) as res:
            report("PUBLIC "+path,{"status":res.status,"network":res.headers.get("X-Amaris-Network")})
    except urllib.error.HTTPError as e:
        report("PUBLIC "+path,{"status":e.code})
    except Exception as e:
        report("PUBLIC "+path,{"error":type(e).__name__})
