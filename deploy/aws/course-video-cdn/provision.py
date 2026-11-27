"""Provision an isolated CloudFront distribution over the existing staging video prefix."""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ACCOUNT = "110156539003"
REGION = "eu-north-1"
STACK = "amaris-staging-course-video-cdn"
BUCKET = f"amaris-mathematics-academy-media-stage-{ACCOUNT}-{REGION}"
PARAMETER = "/amaris/aws-staging/course-cdn/signing-key"
CLUSTER = "amaris-ecs-staging"
SERVICE = "amaris-web-staging-stateless"
POLICY_ID = "CloudFrontReadStagingAcademyVideos"


def private_key(ssm):
    try:
        parameter = ssm.get_parameter(Name=PARAMETER, WithDecryption=True)["Parameter"]
    except ssm.exceptions.ParameterNotFound:
        pem = subprocess.check_output(
            ["openssl", "genpkey", "-quiet", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
            text=True,
        )
        ssm.put_parameter(Name=PARAMETER, Value=pem.strip(), Type="SecureString", Tier="Standard", Overwrite=False)
        return pem
    if parameter["Type"] != "SecureString" or parameter["ARN"].split(":")[4] != ACCOUNT:
        raise RuntimeError("Unexpected CloudFront signing key parameter")
    return parameter["Value"]


def distribution_inputs(session):
    if session.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise RuntimeError("Unexpected AWS account")
    cf = session.client("cloudformation")
    media_stack = cf.describe_stacks(StackName="amaris-staging-course-media")["Stacks"][0]
    outputs = {row["OutputKey"]: row["OutputValue"] for row in media_stack["Outputs"]}
    if outputs["BucketName"] != BUCKET:
        raise RuntimeError("Unexpected staging course media bucket")
    s3 = session.client("s3")
    args = {"Bucket": BUCKET, "ExpectedBucketOwner": ACCOUNT}
    gate = s3.get_public_access_block(**args)["PublicAccessBlockConfiguration"]
    if len(gate) != 4 or not all(gate.values()):
        raise RuntimeError("The media bucket must block all public access")
    if s3.get_bucket_ownership_controls(**args)["OwnershipControls"]["Rules"] != [
        {"ObjectOwnership": "BucketOwnerEnforced"}
    ]:
        raise RuntimeError("Unexpected staging media ownership controls")
    ecs = session.client("ecs")
    service = ecs.describe_services(cluster=CLUSTER, services=[SERVICE])["services"][0]
    if service["status"] != "ACTIVE":
        raise RuntimeError("Unexpected ECS staging service")
    task = ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
    role_arn = task["executionRoleArn"]
    if not re.fullmatch(rf"arn:aws:iam::{ACCOUNT}:role/amaris-[A-Za-z0-9+=,.@_-]+", role_arn):
        raise RuntimeError("Unexpected staging task execution role")
    return cf, s3, role_arn.rsplit("/", 1)[-1]


def bucket_policy(s3):
    try:
        stored = s3.get_bucket_policy(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT)["Policy"]
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchBucketPolicy":
            raise
        return {"Version": "2012-10-17", "Statement": []}
    return json.loads(stored)


def allow_private_origin(s3, distribution_id):
    allowed = {
        "Sid": POLICY_ID,
        "Effect": "Allow",
        "Principal": {"Service": "cloudfront.amazonaws.com"},
        "Action": "s3:GetObject",
        "Resource": f"arn:aws:s3:::{BUCKET}/academy-media/videos/*",
        "Condition": {"StringEquals": {"AWS:SourceArn": f"arn:aws:cloudfront::{ACCOUNT}:distribution/{distribution_id}"}},
    }
    policy = bucket_policy(s3)
    if not isinstance(policy["Statement"], list):
        raise RuntimeError("Unexpected existing media bucket policy format")
    existing = [row for row in policy["Statement"] if row.get("Sid") == POLICY_ID]
    if existing == [allowed]:
        return
    if existing:
        raise RuntimeError("A different CloudFront distribution grant already exists")
    policy["Statement"].append(allowed)
    s3.put_bucket_policy(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT, Policy=json.dumps(policy))
    if bucket_policy(s3) != policy:
        raise RuntimeError("The video-only CloudFront grant did not preserve the original bucket policy")


def main():
    session = boto3.Session(region_name=REGION)
    cf, s3, role_name = distribution_inputs(session)
    pem = private_key(session.client("ssm"))
    public_key = subprocess.check_output(
        ["openssl", "pkey", "-pubout"], input=pem, text=True
    ).strip() + "\n"
    with tempfile.TemporaryDirectory() as directory:
        parameter_file = Path(directory) / "public-parameters.json"
        parameter_file.write_text(json.dumps([
            {"ParameterKey": "MediaBucket", "ParameterValue": BUCKET},
            {"ParameterKey": "ExecutionRoleName", "ParameterValue": role_name},
            {"ParameterKey": "SigningPublicKey", "ParameterValue": public_key},
        ]))
        subprocess.run(
            ["aws", "cloudformation", "deploy", "--stack-name", STACK,
             "--template-file", str(Path(__file__).with_name("stack.yml")),
             "--parameter-overrides", f"file://{parameter_file}",
             "--capabilities", "CAPABILITY_IAM", "--no-fail-on-empty-changeset",
             "--tags", "Application=Amaris-Mathematics-Academy", "Environment=staging"],
            check=True,
        )

    stack = cf.describe_stacks(StackName=STACK)["Stacks"][0]
    outputs = {row["OutputKey"]: row["OutputValue"] for row in stack["Outputs"]}
    cloudfront = session.client("cloudfront")
    cloudfront.get_waiter("distribution_deployed").wait(Id=outputs["DistributionId"])
    allow_private_origin(s3, outputs["DistributionId"])
    with open(os.environ["GITHUB_OUTPUT"], "a") as step:
        for label, key in (("domain", "Domain"), ("key-id", "KeyId"), ("distribution-id", "DistributionId")):
            step.write(f"{label}={outputs[key]}\n")
    print(f"CloudFront is deployed at {outputs['Domain']} with a read grant limited to the staging video prefix.")


if __name__ == "__main__":
    main()
