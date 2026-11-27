"""Write a unique CloudWatch event and match its body in the S3 archive."""
import gzip
import sys
from collections import defaultdict
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import boto3

account = "110156539003"
group = "/amaris/mathematics-academy/staging"
bucket = f"amaris-mathematics-academy-logs-{account}-eu-north-1"
logs = boto3.client("logs")
s3 = boto3.client("s3")
def verify_application_streams():
    expected = {"backend": 2, "frontend": 2, "cms": 2, "celery-beat": 1,
                "celery-worker": 1, "gateway": 1, "staging-shared-valkey": 1}
    now = datetime.now(timezone.utc)
    days = (now, now - timedelta(days=1))
    found = defaultdict(set)
    for attempt in range(30):
        pages = logs.get_paginator("describe_log_streams").paginate(logGroupName=group)
        for page in pages:
            for stream in page["logStreams"]:
                name = stream["logStreamName"]
                parts = name.split("/")
                if len(parts) != 3 or parts[1] not in expected or parts[0] in found[parts[1]]:
                    continue
                for day in days:
                    prefix = f"staging/{day:%Y/%m/%d}/{quote(name, safe='')}/"
                    listing = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1, ExpectedBucketOwner=account)
                    if not listing.get("Contents"):
                        continue
                    key = listing["Contents"][0]["Key"]
                    archived = s3.get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=account)
                    batch = json.loads(gzip.decompress(archived["Body"].read()))
                    assert batch["logGroup"] == group and batch["logStream"] == name
                    assert archived["ServerSideEncryption"] == "AES256" and batch["logEvents"]
                    found[parts[1]].add(parts[0])
                    break
        if all(len(found[service]) >= count for service, count in expected.items()):
            print("Verified actual encrypted S3 archives for " +
                  ", ".join(f"{service} ({len(found[service])} host(s))" for service in expected))
            return
        time.sleep(5)
    raise SystemExit(f"Archived sources found: {[(name, len(found[name])) for name in expected]}")

if sys.argv[1:] == ["--application"]:
    verify_application_streams()
    raise SystemExit(0)

nonce = uuid.uuid4().hex
stream = f"archive-check-{nonce}"
now = datetime.now(timezone.utc)
logs.create_log_stream(logGroupName=group, logStreamName=stream)
logs.put_log_events(logGroupName=group, logStreamName=stream,
                    logEvents=[{"timestamp": int(now.timestamp()*1000), "message": nonce}])
prefix = f"staging/{now:%Y/%m/%d}/{stream}/"
for attempt in range(50):
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, ExpectedBucketOwner=account)
    for obj in response.get("Contents", []):
        archived = s3.get_object(Bucket=bucket, Key=obj["Key"], ExpectedBucketOwner=account)
        batch = json.loads(gzip.decompress(archived["Body"].read()))
        if (batch["logGroup"] == group and batch["logStream"] == stream and
                any(e["message"] == nonce for e in batch["logEvents"])):
            print(f"Verified a real CloudWatch event in s3://{bucket}/{obj['Key']}, encryption {archived['ServerSideEncryption']}.")
            raise SystemExit(0)
    time.sleep(5)
raise SystemExit("The CloudWatch event was not found in the S3 archive within the verification window.")
