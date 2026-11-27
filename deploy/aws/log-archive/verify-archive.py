"""Write a unique CloudWatch event and match its body in the S3 archive."""
import gzip
import json
import time
import uuid
from datetime import datetime, timezone

import boto3

account = "110156539003"
group = "/amaris/mathematics-academy/staging"
bucket = f"amaris-mathematics-academy-logs-{account}-eu-north-1"
logs = boto3.client("logs")
s3 = boto3.client("s3")
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
