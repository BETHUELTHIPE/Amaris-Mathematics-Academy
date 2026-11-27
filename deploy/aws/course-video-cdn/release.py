"""Roll out the verified staging backend and exercise CloudFront from an ECS task."""

import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

import boto3

from provision import ACCOUNT, BUCKET, CLUSTER, PARAMETER, REGION, SERVICE

BASE_BACKEND = "cfdb105761836c7730fec52ada54c58c624206db"
ORIGIN = "https://16.171.164.5"
REGISTRY = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/amaris-staging-frontend"
FAMILY = "amaris-ecs-staging-alb-web"


def http_json(path):
    with urlopen(ORIGIN + path, timeout=12) as response:
        return json.load(response)


def service_state(ecs):
    return ecs.describe_services(cluster=CLUSTER, services=[SERVICE])["services"][0]


def healthy_tasks(ecs, elb, revision):
    state = service_state(ecs)
    if (
        state["status"] != "ACTIVE" or state["desiredCount"] != 2
        or state["runningCount"] != 2 or state["pendingCount"] != 0
        or state["taskDefinition"] != revision
        or len(state["deployments"]) != 1
        or state["deployments"][0].get("rolloutState") != "COMPLETED"
    ):
        return []
    arns = ecs.list_tasks(cluster=CLUSTER, serviceName=SERVICE, desiredStatus="RUNNING")["taskArns"]
    if len(arns) != 2:
        return []
    tasks = ecs.describe_tasks(cluster=CLUSTER, tasks=arns)["tasks"]
    if len(tasks) != 2 or any(
        row["taskDefinitionArn"] != revision or row.get("healthStatus") != "HEALTHY"
        for row in tasks
    ):
        return []
    target = state["loadBalancers"][0]["targetGroupArn"]
    if not target.startswith(f"arn:aws:elasticloadbalancing:{REGION}:{ACCOUNT}:targetgroup/amaris-staging-stateless/"):
        raise RuntimeError("Unexpected staging target group")
    targets = elb.describe_target_health(TargetGroupArn=target)["TargetHealthDescriptions"]
    return tasks if sum(row["TargetHealth"]["State"] == "healthy" for row in targets) == 2 else []


def wait_for_service(ecs, elb, revision):
    deadline = time.monotonic() + 1100
    while time.monotonic() < deadline:
        if tasks := healthy_tasks(ecs, elb, revision):
            return tasks
        state = service_state(ecs)
        if state["taskDefinition"] != revision or any(
            row["taskDefinition"] == revision and row.get("rolloutState") == "FAILED"
            for row in state["deployments"]
        ):
            raise RuntimeError("AWS stopped the candidate rollout")
        time.sleep(15)
    raise RuntimeError("Timed out waiting for the staging ECS service")


def task_configuration(ecs, previous, digest, sha, domain, key_id):
    current = ecs.describe_task_definition(taskDefinition=previous, include=["TAGS"])
    task = current["taskDefinition"]
    if (
        task["family"] != FAMILY or task["networkMode"] != "awsvpc" or task.get("volumes")
        or task["runtimePlatform"]["cpuArchitecture"] != "ARM64"
        or {row["name"] for row in task["containerDefinitions"]} != {"backend", "frontend", "cms"}
    ):
        raise RuntimeError("Unexpected staging ECS task")
    backend = next(row for row in task["containerDefinitions"] if row["name"] == "backend")
    if not backend["image"].startswith(REGISTRY + "@sha256:"):
        raise RuntimeError("The previous backend is outside the verified staging registry")
    backend["image"] = REGISTRY + "@" + digest
    environment = {
        "ACADEMY_VIDEO_CLOUDFRONT_DOMAIN": domain,
        "ACADEMY_VIDEO_CLOUDFRONT_KEY_ID": key_id,
    }
    secret = "ACADEMY_VIDEO_CLOUDFRONT_PRIVATE_KEY"
    backend["environment"] = [
        row for row in backend.get("environment", []) if row["name"] not in {*environment, secret}
    ] + [{"name": key, "value": value} for key, value in environment.items()]
    backend["secrets"] = [
        row for row in backend.get("secrets", []) if row["name"] not in {*environment, secret}
    ] + [{"name": secret, "valueFrom": f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter{PARAMETER}"}]
    wrapper = re.sub(r"export RELEASE_GIT_SHA=[0-9a-f]{40}\n", "", backend["entryPoint"][2])
    if wrapper.count('exec "$@"') != 1 or "export DATABASE_CONN_MAX_AGE=0\n" not in wrapper:
        raise RuntimeError("Unexpected staging task runtime wrapper")
    backend["entryPoint"][2] = wrapper.replace('exec "$@"', f'export RELEASE_GIT_SHA={sha}\nexec "$@"')
    readonly = ("taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities",
                "registeredAt", "registeredBy", "deregisteredAt")
    request = {key: value for key, value in task.items() if key not in readonly}
    tags = [row for row in current.get("tags", []) if not row["key"].startswith("aws:")]
    if tags:
        request["tags"] = tags
    return request


def verify_playback(session, ecs, tasks):
    key = f"academy-media/videos/{uuid.uuid4().hex}.mp4"
    s3 = session.client("s3")
    location = {"Bucket": BUCKET, "Key": key, "ExpectedBucketOwner": ACCOUNT}
    if s3.get_bucket_versioning(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT).get("Status") != "Enabled":
        raise RuntimeError("Refusing to test against an unversioned bucket")
    with Path(os.environ["RUNNER_TEMP"], "amaris-cdn-probe.mp4").open("rb") as file:
        version = s3.put_object(**location, Body=file, ContentType="video/mp4",
                                ServerSideEncryption="AES256", IfNoneMatch="*")["VersionId"]
    try:
        for task in tasks:
            host = ecs.describe_container_instances(
                cluster=CLUSTER, containerInstances=[task["containerInstanceArn"]]
            )["containerInstances"][0]["ec2InstanceId"]
            subprocess.run(
                ["bash", "deploy/aws/ecs/run-on-host.sh", host,
                 "deploy/aws/course-video-cdn/probe-on-host.sh", task["taskArn"].rsplit("/", 1)[-1], key],
                check=True,
            )
    finally:
        s3.delete_object(**location, VersionId=version)
        print("Removed only the isolated CloudFront test object version.", flush=True)


def main():
    sha, digest = os.environ["BACKEND_SHA"], os.environ["BACKEND_DIGEST"]
    domain, key_id = os.environ["VIDEO_CDN_DOMAIN"], os.environ["VIDEO_CDN_KEY_ID"]
    if not all((
        re.fullmatch(r"[0-9a-f]{40}", sha), re.fullmatch(r"sha256:[0-9a-f]{64}", digest),
        re.fullmatch(r"[a-z0-9]+\.cloudfront\.net", domain), re.fullmatch(r"[A-Z0-9]+", key_id),
    )):
        raise RuntimeError("Unexpected staging deployment inputs")
    session = boto3.Session(region_name=REGION)
    if session.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise RuntimeError("Unexpected AWS account")
    ecs, elb = session.client("ecs"), session.client("elbv2")
    state = service_state(ecs)
    previous = state["taskDefinition"]
    previous_tasks = healthy_tasks(ecs, elb, previous)
    baseline = http_json("/health/version/")["git_sha"]
    if not previous_tasks or baseline not in (BASE_BACKEND, sha):
        raise RuntimeError("The running backend does not match the expected staging baseline")
    if not state["deploymentConfiguration"]["deploymentCircuitBreaker"]["rollback"]:
        raise RuntimeError("Staging ECS automatic rollback is not armed")
    if baseline == sha:
        verify_playback(session, ecs, previous_tasks)
        return
    definition = ecs.register_task_definition(**task_configuration(ecs, previous, digest, sha, domain, key_id))
    candidate = definition["taskDefinition"]["taskDefinitionArn"]
    if not healthy_tasks(ecs, elb, previous):
        raise RuntimeError("Staging changed before the ECS update")
    ecs.update_service(cluster=CLUSTER, service=SERVICE, taskDefinition=candidate)
    print(f"Staging started revision {candidate.rsplit('/', 1)[-1]}.", flush=True)
    try:
        tasks = wait_for_service(ecs, elb, candidate)
        if http_json("/health/version/")["git_sha"] != sha or http_json("/health/ready/")["status"] != "ready":
            raise RuntimeError("Public AWS staging did not return the expected healthy backend")
        dependencies = http_json("/health/dependencies/")["dependencies"]
        if not dependencies["postgresql"] or not dependencies["redis"]:
            raise RuntimeError("The staging data dependencies became unhealthy")
        verify_playback(session, ecs, tasks)
    except (Exception, KeyboardInterrupt):
        active = service_state(ecs)["taskDefinition"]
        if active == candidate:
            ecs.update_service(cluster=CLUSTER, service=SERVICE, taskDefinition=previous)
        if active in (candidate, previous):
            wait_for_service(ecs, elb, previous)
            if http_json("/health/version/")["git_sha"] == baseline:
                print("Verified the previous staging backend after rollback.", flush=True)
        raise
    print(f"PASS: {candidate.rsplit('/', 1)[-1]} is healthy on both replicas with signed CDN playback.")


if __name__ == "__main__":
    main()
