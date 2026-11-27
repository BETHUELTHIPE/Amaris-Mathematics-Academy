"""Promote the verified Paystack candidate on the AWS staging ECS service."""

import json
from pathlib import Path
import runpy
import signal
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from botocore.exceptions import ClientError

probe = runpy.run_path(str(Path(__file__).with_name("staging-green-probe.py")))
ecs, elb, session = (probe[name] for name in ("ecs", "elb", "session"))
cluster, service = probe["CLUSTER"], probe["SERVICE"]
baseline, candidate = probe["BASELINE"], probe["CANDIDATE"]
wait_until = probe["wait_until"]
origin = "https://16.171.164.5"
baseline_sha = "cfdb105761836c7730fec52ada54c58c624206db"
candidate_sha = probe["BACKEND_SHA"]
terminal = {"SUCCESSFUL", "STOPPED", "ROLLBACK_SUCCESSFUL", "ROLLBACK_FAILED"}
rollback_states = {"STOP_REQUESTED", "ROLLBACK_REQUESTED", "ROLLBACK_IN_PROGRESS"}


def web():
    info, = ecs.describe_services(cluster=cluster, services=[service])["services"]
    return info


def listen_rules(alb):
    for listener in elb.describe_listeners(LoadBalancerArn=alb)["Listeners"]:
        for page in elb.get_paginator("describe_rules").paginate(ListenerArn=listener["ListenerArn"]):
            for rule in page["Rules"]:
                yield listener, rule


def weights(rule):
    action, = rule["Actions"]
    assert action["Type"] == "forward"
    if config := action.get("ForwardConfig"):
        return {row["TargetGroupArn"]: row.get("Weight", 1) for row in config["TargetGroups"]}
    return {action["TargetGroupArn"]: 1}


def effective_group(rule_arn):
    rule, = elb.describe_rules(RuleArns=[rule_arn])["Rules"]
    group, = (name for name, weight in weights(rule).items() if weight > 0)
    return group


def healthy_count(group):
    return sum(t["TargetHealth"]["State"] == "healthy" for t in probe["targets"](group))


def get_json(path):
    with urlopen(origin + path, timeout=12) as response:
        return json.load(response)


def public_status(path, method="GET"):
    try:
        with urlopen(Request(origin + path, method=method), timeout=12) as response:
            return response.status
    except HTTPError as error:
        return error.code


def public_smoke(expected):
    if get_json("/health/version/")["git_sha"] != expected:
        return False
    deps = get_json("/health/dependencies/")["dependencies"]
    if not deps["postgresql"] or not deps["redis"] or public_status("/") != 200:
        return False
    webhook = "/api/v1/paystack/webhook/"
    return expected == baseline_sha or (
        public_status(webhook) == 405 and public_status(webhook, method="POST") == 403
    )


def settled():
    info = web()
    if info["status"] != "ACTIVE" or info["desiredCount"] != 2 or info["runningCount"] != 2 or info["pendingCount"]:
        return False
    if len(info["deployments"]) != 1:
        return False
    load_balancer, = info["loadBalancers"]
    if advanced := load_balancer.get("advancedConfiguration"):
        active = effective_group(advanced["productionListenerRule"])
    else:
        active = load_balancer["targetGroupArn"]
    revision = info["taskDefinition"].rsplit("/", 1)[-1]
    expected = {baseline: baseline_sha, candidate: candidate_sha}.get(revision)
    return bool(expected and healthy_count(active) == 2 and public_smoke(expected))


def describe_deployment(deployment):
    row, = ecs.describe_service_deployments(serviceDeploymentArns=[deployment])["serviceDeployments"]
    return row


def deployments():
    return ecs.list_service_deployments(cluster=cluster, service=service, maxResults=20)["serviceDeployments"]


def promote(spare):
    info = web()
    assert info["taskDefinition"].endswith("/" + baseline)
    assert info["deploymentController"]["type"] == "ECS"
    assert info["schedulingStrategy"] == "REPLICA"
    assert settled()
    old_lb, = info["loadBalancers"]
    primary = old_lb["targetGroupArn"]
    blue, = elb.describe_target_groups(TargetGroupArns=[primary])["TargetGroups"]
    green, = elb.describe_target_groups(Names=["amaris-staging-web-green"])["TargetGroups"]
    alternate = green["TargetGroupArn"]
    alb, = blue["LoadBalancerArns"]
    assert alb.split("loadbalancer/", 1)[1].startswith("app/amaris-staging-alb/")
    assert green["LoadBalancerArns"] == [alb] and not probe["targets"](alternate)
    old_tasks = probe["service_tasks"]()
    assert len(old_tasks) == 2
    routes = list(listen_rules(alb))
    public_rule, = (
        rule for listener, rule in routes
        if listener["Port"] != 8081 and primary in str(rule["Actions"])
    )
    test_rule, = (
        rule for listener, rule in routes
        if listener["Port"] == 8081 and alternate in str(rule["Actions"])
    )
    assert effective_group(public_rule["RuleArn"]) == primary
    assert effective_group(test_rule["RuleArn"]) == alternate
    lb, = elb.describe_load_balancers(LoadBalancerArns=[alb])["LoadBalancers"]
    nodes = probe["private_alb_nodes"](lb)

    current_hosts = ecs.list_container_instances(cluster=cluster, status="ACTIVE")["containerInstanceArns"]
    hosts = ecs.describe_container_instances(cluster=cluster, containerInstances=current_hosts)["containerInstances"]
    assert any(host["ec2InstanceId"] == spare and host["agentConnected"] for host in hosts)
    current = info["deploymentConfiguration"]
    assert current.get("strategy", "ROLLING") == "ROLLING"
    alarms = current["alarms"]
    assert alarms["enable"] and alarms["rollback"] and len(alarms["alarmNames"]) == 3
    results = session.client("cloudwatch").describe_alarms(AlarmNames=alarms["alarmNames"])["MetricAlarms"]
    assert len(results) == 3 and all(alarm["StateValue"] == "OK" and alarm["ActionsEnabled"] for alarm in results)
    role = session.client("iam").get_role(RoleName="amaris-staging-ecs-bluegreen-lb")["Role"]
    assert role["Arn"] == f"arn:aws:iam::{probe['ACCOUNT']}:role/amaris-staging-ecs-bluegreen-lb"
    assert role["AssumeRolePolicyDocument"]["Statement"][0]["Principal"]["Service"] == "ecs.amazonaws.com"

    service_model = ecs.meta.service_model
    assert "ContinueServiceDeployment" in service_model.operation_names
    config = {
        "strategy": "BLUE_GREEN",
        "maximumPercent": 200,
        "minimumHealthyPercent": 100,
        "bakeTimeInMinutes": 5,
        "alarms": alarms,
        "deploymentCircuitBreaker": {"enable": False, "rollback": False},
        "lifecycleHooks": [{
            "targetType": "PAUSE",
            "lifecycleStages": ["POST_TEST_TRAFFIC_SHIFT"],
            "timeoutConfiguration": {"timeoutInMinutes": 6, "action": "ROLLBACK"},
        }],
    }
    advanced = {
        "alternateTargetGroupArn": alternate,
        "productionListenerRule": public_rule["RuleArn"],
        "testListenerRule": test_rule["RuleArn"],
        "roleArn": role["Arn"],
    }
    previous_deployments = {row["serviceDeploymentArn"] for row in deployments()}
    deployment = None
    try:
        ecs.update_service(
            cluster=cluster,
            service=service,
            taskDefinition=candidate,
            loadBalancers=[{**old_lb, "advancedConfiguration": advanced}],
            deploymentConfiguration=config,
        )
        print("Started native ECS blue-green deployment for the public staging service.", flush=True)

        def discovered():
            histories = [
                row["serviceDeploymentArn"] for row in deployments()
                if row["serviceDeploymentArn"] not in previous_deployments
            ]
            assert len(histories) < 2, "Another staging deployment started concurrently"
            return histories[0] if histories else None

        deployment = wait_until(90, "ECS deployment record not found", discovered)
        last_stage = None

        def hook_ready():
            nonlocal last_stage
            state = describe_deployment(deployment)
            status = state["status"]
            stage = state.get("lifecycleStage")
            if (status, stage) != last_stage:
                last_stage = (status, stage)
                print(f"ECS deployment {status} / {stage}", flush=True)
            if status in terminal | rollback_states:
                raise RuntimeError(f"Deployment stopped before the private check: {status}")
            hooks = [
                row for row in state.get("lifecycleHookDetails", [])
                if row.get("status") == "AWAITING_ACTION" and row.get("targetType") == "PAUSE"
            ]
            assert len(hooks) <= 1
            return hooks[0]["hookId"] if hooks else None

        hook = wait_until(540, "ECS did not reach the private test hook", hook_ready)
        assert old_tasks <= probe["service_tasks"]()
        assert healthy_count(primary) == healthy_count(alternate) == 2
        assert effective_group(public_rule["RuleArn"]) == primary
        assert effective_group(test_rule["RuleArn"]) == alternate
        probe["check_private_route"](nodes)
        assert public_smoke(baseline_sha)
        ecs.continue_service_deployment(serviceDeploymentArn=deployment, hookId=hook, action="CONTINUE")
        print("Passed both private targets and released the staging traffic pause.", flush=True)

        def live_candidate():
            state = describe_deployment(deployment)
            if state["status"] in (terminal - {"SUCCESSFUL"}) | rollback_states:
                raise RuntimeError(f"ECS staging rollout returned {state['status']}")
            try:
                return effective_group(public_rule["RuleArn"]) == alternate and public_smoke(candidate_sha)
            except (URLError, TimeoutError, ValueError):
                return False

        wait_until(150, "The candidate did not pass the public staging smoke", live_candidate)
        print("PASS: the public staging site serves the candidate and rejects unsigned webhook requests.", flush=True)

        def finished():
            status = describe_deployment(deployment)["status"]
            if status in (terminal - {"SUCCESSFUL"}) | rollback_states:
                raise RuntimeError(f"ECS staging rollout returned {status}")
            return status == "SUCCESSFUL" and settled()

        wait_until(420, "ECS did not complete the staging bake", finished)
        print("PASS: ECS reports a successful native blue-green staging deployment.", flush=True)
    except BaseException:
        if deployment:
            status = describe_deployment(deployment)["status"]
            if status not in terminal | rollback_states:
                try:
                    ecs.stop_service_deployment(serviceDeploymentArn=deployment, stopType="ROLLBACK")
                except ClientError as error:
                    print("AWS rollback request returned", error.response["Error"]["Code"], flush=True)
            if status != "SUCCESSFUL":
                wait_until(540, "Staging rollback did not settle", lambda: settled() and public_smoke(baseline_sha))
                print("Staging baseline is healthy after the failed deploy attempt.", flush=True)
        raise


def terminated(signum, _frame):
    raise SystemExit(128 + signum)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminated)
    if sys.argv[1] == "check":
        raise SystemExit(0 if settled() else 1)
    promote(sys.argv[1])
