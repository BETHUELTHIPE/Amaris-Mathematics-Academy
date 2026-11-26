#!/usr/bin/env python3
"""Read-only AWS capacity, task-state and release gates. Never retrieves secret values."""
import json
import subprocess
import sys
from pathlib import Path

CLUSTER = "amaris-ecs-staging"
SERVICE = "amaris-web-staging-alb"
ROOT = Path(__file__).resolve().parent

def aws(*args):
    return json.loads(subprocess.check_output(["aws", *args, "--output", "json"], text=True))

def resources(host, key):
    return {r["name"]: r.get("integerValue", 0) for r in host.get(key, [])}

def requirement(task):
    containers = task["containerDefinitions"]
    return {
        "CPU": max(int(task.get("cpu", 0)), sum(c.get("cpu", 0) for c in containers), 1),
        "MEMORY": max(int(task.get("memory", 0)), sum(c.get("memoryReservation", c.get("memory", 0)) for c in containers), 1),
        "ENI": 1,
    }

def slots(available, need):
    return min(available.get(k, 0) // v for k, v in need.items())

def main():
    if aws("sts", "get-caller-identity")["Account"] != "110156539003":
        raise RuntimeError("Wrong account")
    svc = aws("ecs", "describe-services", "--cluster", CLUSTER, "--services", SERVICE)["services"][0]
    if svc["status"] != "ACTIVE":
        raise RuntimeError("Expected active staging service")
    task = aws("ecs", "describe-task-definition", "--task-definition", svc["taskDefinition"])["taskDefinition"]
    names = {c["name"] for c in task["containerDefinitions"]}
    already_stateless = names == {"backend", "frontend", "cms"} and not task.get("volumes") and all(
        not c.get("mountPoints") for c in task["containerDefinitions"])
    if already_stateless:
        web = task
        jobs_svc = aws("ecs", "describe-services", "--cluster", CLUSTER,
                       "--services", "amaris-staging-singleton-jobs")["services"]
        jobs = aws("ecs", "describe-task-definition", "--task-definition", jobs_svc[0]["taskDefinition"])["taskDefinition"] if jobs_svc else None
    else:
        candidate = json.loads(subprocess.check_output(
            [sys.executable, str(ROOT / "render-multitask.py")], input=json.dumps(task), text=True))
        web, jobs = candidate["web"], candidate["jobs"]
    need = requirement(web)
    jobs_need = requirement(jobs) if jobs else None
    print("Web task reservation:", json.dumps(need), flush=True)
    print("Singleton jobs reservation:", json.dumps(jobs_need), flush=True)
    arns = aws("ecs", "list-container-instances", "--cluster", CLUSTER, "--status", "ACTIVE")["containerInstanceArns"]
    if not arns:
        raise RuntimeError("No ECS hosts")
    hosts = aws("ecs", "describe-container-instances", "--cluster", CLUSTER, "--container-instances", *arns)["containerInstances"]
    connected = [h for h in hosts if h.get("agentConnected") and h["status"] == "ACTIVE"]
    full_slots = 0
    spare_slots = 0
    capacity_known = True
    for i, host in enumerate(connected, 1):
        registered = resources(host, "registeredResources")
        remaining = resources(host, "remainingResources")
        instances = aws("ec2", "describe-instances", "--instance-ids", host["ec2InstanceId"])["Reservations"]
        instance = instances[0]["Instances"][0]
        info = aws("ec2", "describe-instance-types", "--instance-types", instance["InstanceType"])["InstanceTypes"][0]
        max_eni = info["NetworkInfo"]["MaximumNetworkInterfaces"]
        interfaces = instance["NetworkInterfaces"]
        has_trunk = any(n.get("InterfaceType") == "trunk" for n in interfaces)
        if "ENI" not in registered or "ENI" not in remaining:
            if has_trunk:
                capacity_known = False
            else:
                # One primary host ENI; all other interfaces consume direct ENI slots.
                registered["ENI"] = max(0, max_eni - 1)
                remaining["ENI"] = max(0, max_eni - len(interfaces))
        full_slots += slots(registered, need)
        spare_slots += slots(remaining, need)
        print(f"Host {i}: {instance['InstanceType']}, max direct ENIs {max_eni}, attached {len(interfaces)}, trunk {has_trunk}; registered {json.dumps(registered)}, remaining {json.dumps(remaining)}", flush=True)
    subnets = svc.get("networkConfiguration", {}).get("awsvpcConfiguration", {}).get("subnets", [])
    if subnets:
        for i, subnet in enumerate(aws("ec2", "describe-subnets", "--subnet-ids", *subnets)["Subnets"], 1):
            print(f"Application subnet {i}: {subnet['AvailableIpAddressCount']} free IPv4 addresses", flush=True)
    if capacity_known:
        print(f"Connected hosts: {len(connected)}; estimated web slots before singleton jobs/overhead: {full_slots}; currently spare: {spare_slots}", flush=True)
        print(f"At least five task network slots are required for four web replicas and singleton jobs; six or more for rollout overlap.", flush=True)
    else:
        print(f"Connected hosts: {len(connected)}; exact ENI capacity unknown (trunking). Do not interpret missing counters as zero.", flush=True)
    params = aws("ssm", "describe-parameters", "--parameter-filters",
                 "Key=Name,Option=BeginsWith,Values=/amaris/aws-staging/shared-valkey/")["Parameters"]
    expected = {"/amaris/aws-staging/shared-valkey/" + s for s in ("cache", "public-cache", "broker", "result")}
    available = {p["Name"] for p in params if p["Type"] == "SecureString"}
    print(f"Shared Valkey parameters: {len(expected & available)}/4", flush=True)
    plan = aws("freetier", "get-account-plan-state", "--region", "us-east-1")
    print("AWS account plan:", plan.get("accountPlanType"), plan.get("accountPlanStatus"), flush=True)
    print("Service counts:", {k: svc[k] for k in ("desiredCount", "runningCount", "pendingCount")}, flush=True)
    print("Service placement constraints:", len(svc.get("placementConstraints", [])), flush=True)
    target_groups = [l["targetGroupArn"] for l in svc["loadBalancers"]]
    if len(target_groups) != 1:
        raise RuntimeError("Review unexpected target groups")
    targets = aws("elbv2", "describe-target-health", "--target-group-arn", target_groups[0])["TargetHealthDescriptions"]
    healthy = {t["Target"]["Id"] for t in targets if t["TargetHealth"]["State"] == "healthy"}
    task_ids = aws("ecs", "list-tasks", "--cluster", CLUSTER, "--service-name", SERVICE, "--desired-status", "RUNNING")["taskArns"]
    live = aws("ecs", "describe-tasks", "--cluster", CLUSTER, "--tasks", *task_ids)["tasks"] if task_ids else []
    live_ips = {d["value"] for t in live if t["lastStatus"] == "RUNNING" and t["healthStatus"] == "HEALTHY"
                and t["taskDefinitionArn"] == svc["taskDefinition"] for a in t.get("attachments", [])
                if a["type"] == "ElasticNetworkInterface" and a["status"] == "ATTACHED"
                for d in a["details"] if d["name"] == "privateIPv4Address"}
    print(f"Matching healthy ECS/ALB targets: {len(healthy & live_ips)}", flush=True)
    scaling = aws("application-autoscaling", "describe-scalable-targets", "--service-namespace", "ecs",
                  "--scalable-dimension", "ecs:service:DesiredCount", "--resource-ids",
                  f"service/{CLUSTER}/{SERVICE}")["ScalableTargets"]
    gates = {
        "shared Valkey parameters": expected <= available,
        "stateless live web": already_stateless,
        "singleton jobs": bool(already_stateless and jobs and jobs_svc[0]["runningCount"] == jobs_svc[0]["desiredCount"] == 1
                               and jobs_svc[0]["pendingCount"] == 0 and not jobs.get("volumes")
                               and {c["name"] for c in jobs["containerDefinitions"]} == {"celery-worker", "celery-beat"}),
        "two connected hosts": len(connected) >= 2,
        "four healthy web replicas": len(healthy & live_ips) == svc["desiredCount"] == svc["runningCount"] == 4
                                     and svc["pendingCount"] == 0 and len(svc["deployments"]) == 1,
        "2-4 scaling enabled": len(scaling) == 1 and scaling[0]["MinCapacity"] == 2 and scaling[0]["MaxCapacity"] == 4
                               and not scaling[0]["SuspendedState"]["DynamicScalingOutSuspended"],
    }
    for name, passed in gates.items():
        print(("PASS: " if passed else "BLOCKED: ") + name, flush=True)
    return 0 if all(gates.values()) else 1

if __name__ == "__main__":
    sys.exit(main())
