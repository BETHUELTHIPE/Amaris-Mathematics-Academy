"""Register immutable staging revisions, apply the two migrations once, and update jobs."""

import copy
import json
import os
import re
import sys
import time
from urllib.request import urlopen

import boto3

ACCOUNT = "110156539003"
REGION = "eu-north-1"
CLUSTER = "amaris-ecs-staging"
WEB = "amaris-web-staging-stateless"
JOBS = "amaris-staging-singleton-jobs"
OLD_SHA = "164838a3143c22cc7b60ab669e1f0c7dca616a0f"
NEW_SHA = "8f7b34f436c0c1da6cc0bace9c62c89d0712c5d2"
REGISTRY = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/amaris-staging-frontend"
OLD_IMAGE = REGISTRY + "@sha256:bc67977a14b7f91bc5e095715d413367e84595666c96ba41e237e1820df88d30"
FRONTEND = REGISTRY + "@sha256:6a90ef51552b39254b1945d8c3ff8ead5a8889da671122b7184558d56bb586c0"
FIELDS = (
    "family", "taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions", "volumes",
    "placementConstraints", "requiresCompatibilities", "cpu", "memory", "pidMode", "ipcMode",
    "proxyConfiguration", "inferenceAccelerators", "ephemeralStorage", "runtimePlatform", "enableFaultInjection",
)
MIGRATION_COMMAND = """
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

assert settings.SUPABASE_PROJECT_REF == "atyhhjwwxgzeurnwayay", "The database is not the authorised staging project"
assert connection.vendor == "postgresql"
with connection.cursor() as cursor:
    cursor.execute("SET lock_timeout = '4s'")
    cursor.execute("SET statement_timeout = '45s'")
    cursor.execute("SELECT pg_try_advisory_lock(hashtext('amaris-paid-content-staging-migration'))")
    assert cursor.fetchone()[0], "A migration is already running"
    expected = ("0023_private_youtube_lesson_copy", "0024_protect_paid_course_tables")
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    names = tuple(migration.name for migration, backwards in plan if migration.app_label == "content" and not backwards)
    assert len(plan) == len(names) and names in (expected, expected[1:], ()), "Unexpected staging migration plan"
    call_command("migrate", interactive=False, verbosity=1)
    call_command("migrate", check_unapplied=True, interactive=False, verbosity=0)
    print("Verified the staging database migration plan and applied pending paid-content migrations.")
"""
session = boto3.Session(region_name=REGION)
ecs = session.client("ecs")


def site_version():
    with urlopen("https://16.171.164.5/health/version/", timeout=12) as response:
        return json.load(response)["git_sha"]


def service(name):
    item, = ecs.describe_services(cluster=CLUSTER, services=[name])["services"]
    assert item["status"] == "ACTIVE", "Unexpected staging service status"
    return item


def definition(arn):
    task = ecs.describe_task_definition(taskDefinition=arn)["taskDefinition"]
    assert task["networkMode"] == "awsvpc" and task["runtimePlatform"]["cpuArchitecture"] == "ARM64"
    assert not task.get("volumes") and task["family"].startswith("amaris-ecs-staging-")
    return {key: copy.deepcopy(task[key]) for key in FIELDS if key in task and task[key] is not None}


def register(task, purpose):
    response = ecs.register_task_definition(**task, tags=[
        {"key": "Environment", "value": "staging"}, {"key": "Purpose", "value": purpose},
        {"key": "ReleaseGitSha", "value": NEW_SHA},
    ])
    return response["taskDefinition"]["taskDefinitionArn"]


def update_containers(task, kind, image):
    names = {container["name"] for container in task["containerDefinitions"]}
    assert names == ({"backend", "frontend", "cms"} if kind == "web" else {"celery-worker", "celery-beat"})
    for container in task["containerDefinitions"]:
        if container["name"] == "frontend":
            assert container["image"] == FRONTEND
        elif container["name"] != "cms":
            assert container["image"] == OLD_IMAGE and not container.get("mountPoints")
            assert any(entry["name"] == "AMARIS_RUNTIME_ENV" for entry in container["secrets"])
            assert {"name": "PAYSTACK_ENABLED", "value": "false"} in container["environment"]
            wrapper = container["entryPoint"]
            assert wrapper[:2] == ["/bin/sh", "-ec"]
            wrapper[2], changed = re.subn(r"export RELEASE_GIT_SHA=[0-9a-f]{40}\n", f"export RELEASE_GIT_SHA={NEW_SHA}\n", wrapper[2])
            assert changed == 1 and "export PAYSTACK_ENABLED=false" in wrapper[2]
            container["image"] = image


def prepare():
    assert site_version() == OLD_SHA
    digest = os.environ["BACKEND_DIGEST"]
    assert re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
    assert session.client("ecr").describe_images(
        repositoryName="amaris-staging-frontend", imageIds=[{"imageDigest": digest}]
    )["imageDetails"][0]["imageDigest"] == digest
    image = REGISTRY + "@" + digest
    web = service(WEB)
    jobs = service(JOBS)
    assert web["taskDefinition"].endswith("/amaris-ecs-staging-alb-web:17")
    assert jobs["taskDefinition"].endswith("/amaris-ecs-staging-singleton-jobs:3")
    for item, count in ((web, 2), (jobs, 1)):
        assert item["desiredCount"] == item["runningCount"] == count and item["pendingCount"] == 0
        assert len(item["deployments"]) == 1
    web_task, jobs_task = definition(web["taskDefinition"]), definition(jobs["taskDefinition"])
    update_containers(web_task, "web", image)
    update_containers(jobs_task, "jobs", image)
    migration_task = copy.deepcopy(web_task)
    migration_task["family"] = "amaris-ecs-staging-paid-content-migrate"
    backend, = (c for c in migration_task["containerDefinitions"] if c["name"] == "backend")
    for key in ("healthCheck", "portMappings", "dependsOn", "links"):
        backend.pop(key, None)
    backend["command"] = ["python", "-c", MIGRATION_COMMAND]
    migration_task["containerDefinitions"] = [backend]
    revisions = {
        "CANDIDATE_TASK": register(web_task, "paid-content-web"),
        "JOBS_TASK": register(jobs_task, "paid-content-worker-beat"),
        "MIGRATION_TASK": register(migration_task, "paid-content-migration"),
    }
    with open(os.environ["GITHUB_ENV"], "a") as environment:
        for name, revision in revisions.items():
            print(f"{name}: {revision.rsplit('/', 1)[-1]}")
            environment.write(f"{name}={revision}\n")


def migrate():
    web = service(WEB)
    assert web["taskDefinition"].endswith("/amaris-ecs-staging-alb-web:17") and site_version() == OLD_SHA
    network = web["networkConfiguration"]
    task, = ecs.run_task(
        cluster=CLUSTER, taskDefinition=os.environ["MIGRATION_TASK"], launchType="EC2",
        networkConfiguration=network, count=1, startedBy=f"paid-content-{os.environ['GITHUB_RUN_ID']}",
    )["tasks"]
    arn = task["taskArn"]
    try:
        for _ in range(72):
            task, = ecs.describe_tasks(cluster=CLUSTER, tasks=[arn])["tasks"]
            if task["lastStatus"] == "STOPPED":
                backend, = task["containers"]
                assert backend.get("exitCode") == 0, f"Staging migration failed with exit code {backend.get('exitCode')}"
                print("PASS: isolated staging migration task exited successfully.")
                return
            time.sleep(5)
        raise RuntimeError("Staging migration task did not finish in time")
    finally:
        if task["lastStatus"] != "STOPPED":
            ecs.stop_task(cluster=CLUSTER, task=arn, reason="Staging migration verification timeout")


def jobs():
    assert site_version() == NEW_SHA and service(WEB)["taskDefinition"] == os.environ["CANDIDATE_TASK"]
    before = service(JOBS)
    prior = before["taskDefinition"]
    assert prior.endswith("/amaris-ecs-staging-singleton-jobs:3")
    deployment = before["deploymentConfiguration"]
    assert deployment["minimumHealthyPercent"] == 0 and deployment["maximumPercent"] == 100
    assert before["desiredCount"] == 1
    after = os.environ["JOBS_TASK"]

    def wait_ready(revision):
        for _ in range(40):
            state = service(JOBS)
            if state["runningCount"] == 1 and state["pendingCount"] == 0 and len(state["deployments"]) == 1:
                active = state["deployments"][0]
                if active["taskDefinition"] == revision and active.get("rolloutState") == "COMPLETED":
                    arns = ecs.list_tasks(cluster=CLUSTER, serviceName=JOBS, desiredStatus="RUNNING")["taskArns"]
                    if len(arns) == 1:
                        task, = ecs.describe_tasks(cluster=CLUSTER, tasks=arns)["tasks"]
                        if task["taskDefinitionArn"] == revision and {
                            c["name"] for c in task["containers"]
                            if c["lastStatus"] == "RUNNING" and c.get("healthStatus") == "HEALTHY"
                        } == {"celery-worker", "celery-beat"}:
                            return
            time.sleep(8)
        raise RuntimeError("Singleton worker and Beat failed to reach healthy state")

    wait_ready(prior)
    ecs.update_service(cluster=CLUSTER, service=JOBS, taskDefinition=after)
    try:
        wait_ready(after)
    except BaseException:
        ecs.update_service(cluster=CLUSTER, service=JOBS, taskDefinition=prior)
        wait_ready(prior)
        print("Verified rollback of the singleton staging task.")
        raise
    print("PASS: one healthy worker and one healthy Beat from the new release.")


if __name__ == "__main__":
    assert session.client("sts").get_caller_identity()["Account"] == ACCOUNT
    {"prepare": prepare, "migrate": migrate, "jobs": jobs}[sys.argv[1]]()
