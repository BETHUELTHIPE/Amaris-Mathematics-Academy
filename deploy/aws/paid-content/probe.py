"""Check the exact paid-content backend running on each web host."""

import os
import subprocess

import boto3

cluster = "amaris-ecs-staging"
service = "amaris-web-staging-stateless"
ecs = boto3.client("ecs", region_name="eu-north-1")
tasks = ecs.list_tasks(cluster=cluster, serviceName=service, desiredStatus="RUNNING")["taskArns"]
rows = ecs.describe_tasks(cluster=cluster, tasks=tasks)["tasks"]
candidate = os.environ["CANDIDATE_TASK"]
rows = [row for row in rows if row["taskDefinitionArn"] == candidate and row["lastStatus"] == "RUNNING"]
assert len(rows) == 2
for row in rows:
    host, = ecs.describe_container_instances(
        cluster=cluster, containerInstances=[row["containerInstanceArn"]]
    )["containerInstances"]
    subprocess.run([
        "bash", "deploy/aws/ecs/run-on-host.sh", host["ec2InstanceId"],
        "deploy/aws/paid-content/probe-on-host.sh", row["taskArn"].rsplit("/", 1)[-1],
        os.environ["PAID_PROBE_KEY"], os.environ["PAID_PROBE_SHA"],
    ], check=True)
