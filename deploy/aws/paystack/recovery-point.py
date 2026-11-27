"""Capture only the pinned staging application schema; no database credentials leave ECS."""
import base64
import hashlib
import json
import os
import re
import shlex
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

ACCOUNT = "110156539003"
REGION = "eu-north-1"
BUCKET = f"amaris-staging-db-recovery-{ACCOUNT}-{REGION}"
CLUSTER = "amaris-ecs-staging"
SERVICE = "amaris-web-staging-stateless"
BASELINE = "cfdb105761836c7730fec52ada54c58c624206db"
ROOT = Path(os.environ["RUNNER_TEMP"]) / "amaris-paystack-recovery"
ROOT.mkdir(mode=0o700, exist_ok=True)
session = boto3.Session(region_name=REGION)
assert session.client("sts").get_caller_identity()["Account"] == ACCOUNT
ecs = session.client("ecs")
s3 = session.client("s3", endpoint_url=f"https://s3.{REGION}.amazonaws.com",
                    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
ssm = session.client("ssm")
state = ecs.describe_services(cluster=CLUSTER, services=[SERVICE])["services"][0]
assert state["status"] == "ACTIVE" and state["desiredCount"] == state["runningCount"] == 2 and state["pendingCount"] == 0
from urllib.request import urlopen
with urlopen("https://16.171.164.5/health/version/", timeout=12) as r:
    assert json.load(r)["git_sha"] == BASELINE, "Unexpected AWS baseline"
try:
    s3.head_bucket(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT)
except ClientError as e:
    if e.response["Error"]["Code"] not in ("404", "NotFound", "NoSuchBucket"):
        raise
    s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION},
                     ObjectOwnership="BucketOwnerEnforced")
    s3.put_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
    s3.put_bucket_versioning(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT, VersioningConfiguration={"Status": "Enabled"})
args = {"Bucket": BUCKET, "ExpectedBucketOwner": ACCOUNT}
assert all(s3.get_public_access_block(**args)["PublicAccessBlockConfiguration"].values())
assert s3.get_bucket_versioning(**args)["Status"] == "Enabled"
assert s3.get_bucket_encryption(**args)["ServerSideEncryptionConfiguration"]["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
assert s3.get_bucket_ownership_controls(**args)["OwnershipControls"]["Rules"] == [{"ObjectOwnership":"BucketOwnerEnforced"}]
try:
    assert not s3.get_bucket_policy_status(**args)["PolicyStatus"]["IsPublic"]
except ClientError as e:
    if e.response["Error"]["Code"] != "NoSuchBucketPolicy":
        raise
key = f"application/backup-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}.dump"
# Short-lived, object-specific write-only URL; never print it. No DB password leaves the live task.
url = s3.generate_presigned_url("put_object", Params={"Bucket": BUCKET, "Key": key,
    "ServerSideEncryption": "AES256", "IfNoneMatch": "*"}, ExpiresIn=300, HttpMethod="PUT")
tasks = ecs.list_tasks(cluster=CLUSTER, serviceName=SERVICE, desiredStatus="RUNNING")["taskArns"]
assert len(tasks) == 2
task = ecs.describe_tasks(cluster=CLUSTER, tasks=[tasks[0]])["tasks"][0]
assert task["taskDefinitionArn"] == state["taskDefinition"]
host = ecs.describe_container_instances(cluster=CLUSTER, containerInstances=[task["containerInstanceArn"]])["containerInstances"][0]["ec2InstanceId"]
tid = task["taskArn"].rsplit("/",1)[-1]
assert re.fullmatch("[a-f0-9]{32}", tid)
script = """set -euo pipefail
umask 077
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
backend=$(docker ps -q --filter label=com.amazonaws.ecs.task-arn=arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/""" + tid + """ --filter label=com.amazonaws.ecs.container-name=backend)
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
if ! docker exec -i "$backend" python - > "$work/app.dump" 2>"$work/dump.err" <<'PY'
import os, re, subprocess, sys
from urllib.parse import urlsplit
for line in os.environ.pop("AMARIS_RUNTIME_ENV", "").splitlines():
    k, sep, v = line.partition("=")
    if sep:
        os.environ.setdefault(k,v)
url = urlsplit(os.environ["DATABASE_URL"])
ref = "atyhhjwwxgzeurnwayay"
host = url.hostname or ""
assert url.scheme in ("postgres","postgresql") and url.path == "/postgres"
assert host == "db."+ref+".supabase.co" or (host.endswith(".pooler.supabase.com") and (url.username or "").endswith("."+ref))
schema = os.getenv("DATABASE_SCHEMA","").strip() or "public"
assert re.fullmatch("[A-Za-z_][A-Za-z0-9_]*",schema)
assert schema not in ("auth","storage","vault","extensions","pg_catalog","information_schema") and "prod" not in schema.lower()
env = dict(os.environ, PGSSLMODE="require", PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=120000")
# No source credentials are included in shell/SSM command arguments or output.
subprocess.run(["pg_dump","--dbname="+os.environ["DATABASE_URL"],"--schema="+schema,"--format=custom","--no-owner","--no-acl","--lock-wait-timeout=5s"],env=env,check=True,timeout=150)
PY
then echo 'BLOCKED: source dump failed (details withheld)'; exit 1; fi
test -s "$work/app.dump"
status=$(curl --fail --silent --show-error --max-time 120 -X PUT -H 'x-amz-server-side-encryption: AES256' -H 'If-None-Match: *' --upload-file "$work/app.dump" """ + shlex.quote(url) + """ -o "$work/upload-response" -w '%{http_code}' 2>"$work/upload.err") || { echo 'BLOCKED: private encrypted backup upload failed'; exit 1; }
[[ "$status" == 200 ]] || { echo "BLOCKED: S3 PUT returned HTTP $status"; exit 1; }
printf 'PASS: staging dump uploaded; bytes='
wc -c < "$work/app.dump"
"""
encoded = base64.b64encode(script.encode()).decode()
response = ssm.send_command(InstanceIds=[host], DocumentName="AWS-RunShellScript", TimeoutSeconds=90,
    Parameters={"commands":["printf '%s' "+shlex.quote(encoded)+" | base64 -d | bash"],"executionTimeout":["300"]},
    Comment="Capture staging application recovery point (no database credential in command)")
command = response["Command"]["CommandId"]
for _ in range(75):
    time.sleep(4)
    try:
        result = ssm.get_command_invocation(CommandId=command, InstanceId=host)
    except ssm.exceptions.InvocationDoesNotExist:
        continue
    if result["Status"] == "Success":
        match = re.fullmatch(r"PASS: staging dump uploaded; bytes=\s*([0-9]+)", result.get("StandardOutputContent","").strip())
        if not match or int(match.group(1)) <= 0:
            raise SystemExit("BLOCKED: remote command completed without verified upload marker")
        print("PASS: remote S3 PUT returned 200; uploaded bytes:", match.group(1))
        break
    if result["Status"] not in ("Pending","InProgress","Delayed"):
        safe = [line for line in result.get("StandardOutputContent","").splitlines() if re.fullmatch(r"BLOCKED: [A-Za-z0-9 ();:-]+",line)]
        print("\n".join(safe))
        raise SystemExit("BLOCKED: remote backup command "+result["Status"])
else:
    ssm.cancel_command(CommandId=command)
    raise SystemExit("BLOCKED: backup command timeout")
head = s3.head_object(**args, Key=key)
assert head["ServerSideEncryption"] == "AES256" and head["ContentLength"] == int(match.group(1)) and head.get("VersionId")
s3.download_file(BUCKET,key,str(ROOT/"app.dump"),ExtraArgs={"VersionId":head["VersionId"],"ExpectedBucketOwner":ACCOUNT})
assert (ROOT/"app.dump").stat().st_size == head["ContentLength"]
(ROOT/"app.dump").chmod(0o600)
(ROOT/"location.json").write_text(json.dumps({"bucket":BUCKET,"key":key,"version":head["VersionId"]}))
print("PASS: versioned encrypted staging recovery point captured; no database data in workflow logs.")
