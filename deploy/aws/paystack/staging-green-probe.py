"""Test the two immutable Paystack web tasks through the private staging listener."""

import ipaddress
import os
import shlex
import signal
import sys
import time

import boto3

ACCOUNT = "110156539003"
REGION = "eu-north-1"
CLUSTER = "amaris-ecs-staging"
SERVICE = "amaris-web-staging-stateless"
VPC = "vpc-0252538d2febd4641"
EDGE = "i-02855f007d15af597"
EDGE_GROUP = "sg-037ced8e9b8da3084"
BASELINE = "amaris-ecs-staging-alb-web:14"
CANDIDATE = "amaris-ecs-staging-alb-web:17"
BACKEND_SHA = "164838a3143c22cc7b60ab669e1f0c7dca616a0f"
BACKEND_DIGEST = "sha256:bc67977a14b7f91bc5e095715d413367e84595666c96ba41e237e1820df88d30"
FRONTEND_DIGEST = "sha256:6a90ef51552b39254b1945d8c3ff8ead5a8889da671122b7184558d56bb586c0"
TAG = "paystack-green-" + os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]

session = boto3.Session(region_name=REGION)
assert session.client("sts").get_caller_identity()["Account"] == ACCOUNT
ecs = session.client("ecs")
elb = session.client("elbv2")
ec2 = session.client("ec2")
ssm = session.client("ssm")


def targets(group):
    return elb.describe_target_health(TargetGroupArn=group)["TargetHealthDescriptions"]


def service_tasks():
    return set(ecs.list_tasks(cluster=CLUSTER, serviceName=SERVICE, desiredStatus="RUNNING")["taskArns"])


def check_blue(primary, original):
    web, = ecs.describe_services(cluster=CLUSTER, services=[SERVICE])["services"]
    assert web["taskDefinition"].endswith("/" + BASELINE), "Baseline task definition changed"
    assert web["runningCount"] == web["desiredCount"] == 2 and not web["pendingCount"]
    assert service_tasks() == original, "Original blue tasks changed during the private probe"
    assert sum(t["TargetHealth"]["State"] == "healthy" for t in targets(primary)) == 2


def wait_until(seconds, description, check, interval=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval)
    raise RuntimeError(description)


def task_address(task):
    for attachment in task["attachments"]:
        if attachment["type"] == "ElasticNetworkInterface" and attachment["status"] == "ATTACHED":
            details = {item["name"]: item["value"] for item in attachment["details"]}
            if address := details.get("privateIPv4Address"):
                assert ipaddress.ip_address(address).is_private
                return address
    return None


def private_alb_nodes(load_balancer):
    assert load_balancer["VpcId"] == VPC
    groups = ec2.describe_security_groups(GroupIds=load_balancer["SecurityGroups"])["SecurityGroups"]
    protected = False
    for group in groups:
        for rule in group["IpPermissions"]:
            covers_port = rule["IpProtocol"] == "-1" or (
                rule["IpProtocol"] in {"tcp", "6"} and rule["FromPort"] <= 8081 <= rule["ToPort"]
            )
            if covers_port:
                assert not any(rule.get(field) for field in ("IpRanges", "Ipv6Ranges", "PrefixListIds"))
                peers = {peer["GroupId"] for peer in rule.get("UserIdGroupPairs", [])}
                assert peers <= {EDGE_GROUP}, "The test listener allows another source"
                protected |= EDGE_GROUP in peers
    assert protected, "The green test listener must be restricted to the staging edge"
    resource = load_balancer["LoadBalancerArn"].split("loadbalancer/", 1)[1]
    interfaces = [
        interface
        for page in ec2.get_paginator("describe_network_interfaces").paginate(Filters=[
            {"Name": "description", "Values": ["ELB " + resource]},
            {"Name": "vpc-id", "Values": [VPC]},
            {"Name": "status", "Values": ["in-use"]},
        ])
        for interface in page["NetworkInterfaces"]
    ]
    nodes = sorted({interface["PrivateIpAddress"] for interface in interfaces})
    assert 1 <= len(nodes) <= 8 and all(ipaddress.ip_address(ip).is_private for ip in nodes)
    return nodes


def check_private_route(nodes):
    script = """set -euo pipefail
request() {
  curl --noproxy '*' --silent --show-error --max-time 10 -H 'Host: 16.171.164.5' "$@"
}
for ip in NODE_ADDRESSES; do
  origin="http://$ip:8081"
  request --fail "$origin/health/version/" | python3 -c 'import json,sys; assert json.load(sys.stdin)["git_sha"] == "SHA"'
  request --fail "$origin/health/dependencies/" | python3 -c 'import json,sys; d=json.load(sys.stdin)["dependencies"]; assert d["postgresql"] and d["redis"]'
  root_status="$(request -o /dev/null -w '%{http_code}' "$origin/")"
  get_status="$(request -o /dev/null -w '%{http_code}' "$origin/api/v1/paystack/webhook/")"
  post_status="$(request -o /dev/null -w '%{http_code}' -X POST "$origin/api/v1/paystack/webhook/")"
  echo "Private candidate root=$root_status webhook GET=$get_status unsigned POST=$post_status"
  [[ "$root_status" == 200 && "$get_status" == 405 && "$post_status" == 403 ]]
done
echo 'PASS: private candidate version, frontend, PostgreSQL, Redis and webhook checks.'
""".replace("NODE_ADDRESSES", " ".join(nodes)).replace("SHA", BACKEND_SHA)
    command = ssm.send_command(
        InstanceIds=[EDGE],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": ["bash -c " + shlex.quote(script)], "executionTimeout": ["65"]},
        TimeoutSeconds=85,
    )["Command"]["CommandId"]

    def completed():
        try:
            result = ssm.get_command_invocation(CommandId=command, InstanceId=EDGE)
        except ssm.exceptions.InvocationDoesNotExist:
            return None
        if result["Status"] in {"Pending", "InProgress", "Delayed"}:
            return None
        print(result.get("StandardOutputContent", "").strip(), flush=True)
        assert result["Status"] == "Success", f"Private candidate smoke failed: {result['Status']}"
        return True

    wait_until(95, "Private candidate smoke timed out", completed, interval=4)


def main(spare):
    web, = ecs.describe_services(cluster=CLUSTER, services=[SERVICE])["services"]
    load_balancer, = web["loadBalancers"]
    assert load_balancer["containerName"] == "cms" and load_balancer["containerPort"] == 8080
    if spare != "preflight":
        assert not load_balancer.get("advancedConfiguration")
    primary = load_balancer["targetGroupArn"]
    blue, = elb.describe_target_groups(TargetGroupArns=[primary])["TargetGroups"]
    green, = elb.describe_target_groups(Names=["amaris-staging-web-green"])["TargetGroups"]
    assert blue["VpcId"] == green["VpcId"] == VPC and green["TargetType"] == "ip" and green["Port"] == 8080
    alb, = blue["LoadBalancerArns"]
    assert green["LoadBalancerArns"] == [alb]
    alternate = green["TargetGroupArn"]
    assert not targets(alternate), "The private green group is already in use"
    listeners = elb.describe_listeners(LoadBalancerArn=alb)["Listeners"]
    advanced = load_balancer.get("advancedConfiguration")
    green_rules = []
    for listener in listeners:
        for page in elb.get_paginator("describe_rules").paginate(ListenerArn=listener["ListenerArn"]):
            for rule in page["Rules"]:
                if advanced and rule["RuleArn"] == advanced["productionListenerRule"]:
                    # After rollback ECS keeps the alternate in the public rule at zero weight.
                    for action in rule["Actions"]:
                        weights = action.get("ForwardConfig", {}).get("TargetGroups", [])
                        mentions_alternate = alternate in str(action)
                        assert not mentions_alternate or any(
                            row["TargetGroupArn"] == alternate and row.get("Weight") == 0 for row in weights
                        )
                    continue
                is_test = rule["RuleArn"] == advanced["testListenerRule"] if advanced else alternate in str(rule["Actions"])
                if is_test:
                    assert listener["Port"] == 8081 and listener["Protocol"] == "HTTP"
                    assert not rule["IsDefault"]
                    green_rules.append(rule)
                else:
                    assert alternate not in str(rule["Actions"]), "The green group has an unexpected listener rule"
    assert len(green_rules) == 1, "Expected one private rule for the green group"
    if advanced:
        assert advanced["alternateTargetGroupArn"] == alternate
    lb, = elb.describe_load_balancers(LoadBalancerArns=[alb])["LoadBalancers"]
    nodes = private_alb_nodes(lb)
    baseline = service_tasks()
    assert len(baseline) == 2
    check_blue(primary, baseline)

    network = web["networkConfiguration"]
    awsvpc = network["awsvpcConfiguration"]
    assert awsvpc.get("assignPublicIp", "DISABLED") == "DISABLED"
    subnets = ec2.describe_subnets(SubnetIds=awsvpc["subnets"])["Subnets"]
    assert all(subnet["VpcId"] == VPC and not subnet["MapPublicIpOnLaunch"] for subnet in subnets)
    cidrs = [ipaddress.ip_network(subnet["CidrBlock"]) for subnet in subnets]
    candidate = ecs.describe_task_definition(taskDefinition=CANDIDATE)["taskDefinition"]
    assert candidate["runtimePlatform"]["cpuArchitecture"] == "ARM64"
    assert not candidate["volumes"]
    backend, = (item for item in candidate["containerDefinitions"] if item["name"] == "backend")
    frontend, = (item for item in candidate["containerDefinitions"] if item["name"] == "frontend")
    assert backend["image"].endswith("@" + BACKEND_DIGEST)
    assert frontend["image"].endswith("@" + FRONTEND_DIGEST)
    assert {"name": "PAYSTACK_ENABLED", "value": "false"} in backend["environment"]
    assert "export PAYSTACK_ENABLED=false" in backend["entryPoint"][2]

    if spare == "preflight":
        print("PASS: staging route is restricted to the private edge and the candidate is pinned.")
        return

    probe_tasks = []
    registrations = []
    try:
        response = ecs.run_task(
            cluster=CLUSTER,
            launchType="EC2",
            taskDefinition=candidate["taskDefinitionArn"],
            networkConfiguration=network,
            placementStrategy=[{"type": "spread", "field": "instanceId"}],
            count=2,
            startedBy=TAG,
            clientToken=TAG,
            tags=[{"key": "Environment", "value": "staging"}, {"key": "Purpose", "value": "paystack-green-probe"}],
        )
        probe_tasks = [task["taskArn"] for task in response["tasks"]]
        if response["failures"] or len(probe_tasks) != 2:
            reasons = [failure.get("reason", "unknown") for failure in response["failures"]]
            raise RuntimeError(f"Placed {len(probe_tasks)} of two candidate tasks: {reasons}")
        print("PASS: ECS placed both candidate tasks alongside the original replicas.", flush=True)

        def running():
            check_blue(primary, baseline)
            tasks = ecs.describe_tasks(cluster=CLUSTER, tasks=probe_tasks)["tasks"]
            for task in tasks:
                if task["lastStatus"] == "STOPPED":
                    summary = [(c["name"], c.get("exitCode")) for c in task["containers"]]
                    category = task.get("stoppedReason", "").split(":", 1)[0]
                    raise RuntimeError(f"Candidate stopped: {task.get('stopCode')} / {category} / {summary}")
            if len(tasks) == 2 and all(task["lastStatus"] == "RUNNING" and task_address(task) for task in tasks):
                return tasks
            return None

        running_tasks = wait_until(270, "Both candidate containers did not reach RUNNING", running)
        placement = ecs.describe_container_instances(
            cluster=CLUSTER,
            containerInstances=list({task["containerInstanceArn"] for task in running_tasks}),
        )["containerInstances"]
        assert spare in {host["ec2InstanceId"] for host in placement}
        registrations = [{"Id": task_address(task), "Port": 8080} for task in running_tasks]
        assert len({row["Id"] for row in registrations}) == 2
        assert all(any(ipaddress.ip_address(row["Id"]) in cidr for cidr in cidrs) for row in registrations)
        elb.register_targets(TargetGroupArn=alternate, Targets=registrations)

        def healthy_green():
            running()
            descriptions = targets(alternate)
            return len(descriptions) == 2 and all(t["TargetHealth"]["State"] == "healthy" for t in descriptions)

        wait_until(220, "Both green targets did not become healthy", healthy_green)
        print("PASS: both candidate targets are healthy on the private green listener.", flush=True)
        check_private_route(nodes)
        check_blue(primary, baseline)
    finally:
        if registrations:
            elb.deregister_targets(TargetGroupArn=alternate, Targets=registrations)
        # Recover the task ARNs from ECS if the RunTask call reached AWS before the runner lost its response.
        found = ecs.list_tasks(cluster=CLUSTER, startedBy=TAG)["taskArns"]
        probe_tasks = list(set(probe_tasks + found))
        if probe_tasks:
            for task in ecs.describe_tasks(cluster=CLUSTER, tasks=probe_tasks)["tasks"]:
                if task["lastStatus"] != "STOPPED":
                    ecs.stop_task(cluster=CLUSTER, task=task["taskArn"], reason="Private staging green probe completed")
            ecs.get_waiter("tasks_stopped").wait(
                cluster=CLUSTER, tasks=probe_tasks, WaiterConfig={"Delay": 6, "MaxAttempts": 20}
            )
        check_blue(primary, baseline)
        print("PASS: private probe tasks stopped and both original targets are healthy.", flush=True)


def terminate(signum, _frame):
    raise SystemExit(128 + signum)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    main(sys.argv[1])
