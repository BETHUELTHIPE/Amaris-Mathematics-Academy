"""Verify staging S3 alerts using temporary, versioned test objects."""

import hashlib
import json
import time
import uuid
from collections import Counter

import boto3

from configure import (ACCOUNT, ARCHIVE, MEDIA, REGION, STACK, NOTIFICATION_ID,
                       S3_EVENTS, notification_configuration, stack_outputs)


def event_for(bucket, kind):
    return {
        "version": "0",
        "id": str(uuid.uuid4()),
        "detail-type": kind,
        "source": "aws.s3",
        "account": ACCOUNT,
        "time": "2026-01-01T00:00:00Z",
        "region": REGION,
        "resources": [f"arn:aws:s3:::{bucket}"],
        "detail": {"bucket": {"name": bucket}, "object": {"key": "test"}},
    }


def verify_rule(session, rule_name):
    events = session.client("events")
    rule = events.describe_rule(Name=rule_name)
    if rule["State"] != "ENABLED":
        raise RuntimeError("The S3 EventBridge rule is disabled")
    pattern = rule["EventPattern"]
    for bucket in (MEDIA, ARCHIVE):
        if not events.test_event_pattern(
            EventPattern=pattern, Event=json.dumps(event_for(bucket, "Async Copy Completion"))
        )["Result"]:
            raise RuntimeError("AWS EventBridge did not match asynchronous copy completion")
    excluded = (
        event_for("unrelated-bucket", "Async Copy Completion"),
        event_for(MEDIA, "Object Created"),
        event_for(MEDIA, "AWS API Call via CloudTrail"),
    )
    for event in excluded:
        if events.test_event_pattern(EventPattern=pattern, Event=json.dumps(event))["Result"]:
            raise RuntimeError("The EventBridge rule matched an event outside its scope")
    print("AWS EventBridge confirmed copy-completion coverage and bucket isolation.", flush=True)


def write_fixture(s3, bucket, key, tagging, expected):
    location = {"Bucket": bucket, "Key": key, "ExpectedBucketOwner": ACCOUNT}
    versions = []
    try:
        for number in range(2 if tagging else 1):
            result = s3.put_object(**location, Body=f"Amaris staging S3 alert test {number}\n".encode(),
                                   ContentType="text/plain", ServerSideEncryption="AES256")
            versions.append(result["VersionId"])
            expected[bucket, "Object Created"] += 1

        if tagging:
            current = {**location, "VersionId": versions[-1]}
            s3.put_object_tagging(**current, Tagging={"TagSet": [{"Key": "Purpose", "Value": "StagingAlertTest"}]})
            expected[bucket, "Object Tags Added"] += 1
            s3.delete_object_tagging(**current)
            expected[bucket, "Object Tags Deleted"] += 1
    finally:
        for version in versions:
            s3.delete_object(**location, VersionId=version)
            expected[bucket, "Object Deleted"] += 1


def verify_sns_receipts(logs, log_group, keys, expected, start_time):
    hashes = {bucket: hashlib.sha256(key.encode()).hexdigest() for bucket, key in keys.items()}
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        rows = {}
        for page in logs.get_paginator("filter_log_events").paginate(
            logGroupName=log_group, startTime=start_time, filterPattern='"sns_accepted"'
        ):
            for entry in page["events"]:
                try:
                    row = json.loads(entry["message"])
                except ValueError:
                    continue
                if row.get("status") == "sns_accepted" and row.get("bucket") in hashes:
                    if row.get("key_sha256") == hashes[row["bucket"]] and row.get("sns_message_id"):
                        rows[row["event_id"]] = row
        counts = Counter((row["bucket"], row["event"]) for row in rows.values())
        if counts >= expected:
            for (bucket, kind), count in sorted(expected.items()):
                print(f"SNS accepted {count} live {kind} event(s) from {bucket}.", flush=True)
            return
        time.sleep(12)
    missing = {f"{bucket}: {kind}": count for (bucket, kind), count in (expected - counts).items()}
    raise RuntimeError(f"SNS receipts did not arrive for: {missing}")


def main():
    session = boto3.Session(region_name=REGION)
    outputs = stack_outputs(session.client("cloudformation"), STACK)
    verify_rule(session, outputs["Rule"])
    keys = {bucket: f"staging-s3-alert-smoke/{uuid.uuid4().hex}.txt" for bucket in (MEDIA, ARCHIVE)}
    expected = Counter()
    s3 = session.client("s3")
    for bucket in keys:
        config = notification_configuration(s3, bucket)
        queue = next(row for row in config["QueueConfigurations"] if row["Id"] == NOTIFICATION_ID)
        if queue["QueueArn"] != outputs["QueueArn"] or set(queue["Events"]) != set(S3_EVENTS):
            raise RuntimeError("A bucket is missing its staging S3 queue notifications")
    start_time = int(time.time() * 1000)
    for bucket, key in keys.items():
        write_fixture(s3, bucket, key, tagging=bucket == MEDIA, expected=expected)
    print("Removed temporary object versions from both staging buckets.", flush=True)
    verify_sns_receipts(session.client("logs"), outputs["FunctionLogs"], keys, expected, start_time)
    print("PASS: S3 object notifications to SQS to Lambda to the confirmed SNS topic.", flush=True)


if __name__ == "__main__":
    main()
