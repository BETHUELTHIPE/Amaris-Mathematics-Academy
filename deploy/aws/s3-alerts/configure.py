"""Validate and enable EventBridge for the two existing Academy staging buckets."""

import argparse
import time

import boto3

ACCOUNT = "110156539003"
REGION = "eu-north-1"
STACK = "amaris-staging-s3-object-alerts"
ARCHIVE = f"amaris-mathematics-academy-logs-{ACCOUNT}-{REGION}"
MEDIA = f"amaris-mathematics-academy-media-stage-{ACCOUNT}-{REGION}"
TOPIC = f"arn:aws:sns:{REGION}:{ACCOUNT}:amaris-staging-cloudwatch-alarms"


def notification_configuration(s3, bucket):
    config = s3.get_bucket_notification_configuration(Bucket=bucket, ExpectedBucketOwner=ACCOUNT)
    config.pop("ResponseMetadata", None)
    return config


def enable_eventbridge(s3, bucket):
    existing = notification_configuration(s3, bucket)
    if "EventBridgeConfiguration" in existing:
        return False
    updated = {**existing, "EventBridgeConfiguration": {}}
    s3.put_bucket_notification_configuration(
        Bucket=bucket, ExpectedBucketOwner=ACCOUNT, NotificationConfiguration=updated
    )
    if notification_configuration(s3, bucket) != updated:
        raise RuntimeError("The bucket notification configuration did not match the intended update")
    return True


def stack_outputs(cloudformation, name):
    stack = cloudformation.describe_stacks(StackName=name)["Stacks"][0]
    if stack["StackStatus"] not in ("CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"):
        raise RuntimeError(f"Unstable CloudFormation stack {name}")
    return {row["OutputKey"]: row["OutputValue"] for row in stack["Outputs"]}


def preflight(session):
    if session.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise RuntimeError("Unexpected AWS account")
    cloudformation = session.client("cloudformation")
    if stack_outputs(cloudformation, "amaris-staging-log-archive").get("Bucket") != ARCHIVE:
        raise RuntimeError("Unexpected staging archive bucket")
    if stack_outputs(cloudformation, "amaris-staging-course-media").get("BucketName") != MEDIA:
        raise RuntimeError("Unexpected staging media bucket")
    s3 = session.client("s3")
    for bucket in (ARCHIVE, MEDIA):
        kwargs = {"Bucket": bucket, "ExpectedBucketOwner": ACCOUNT}
        if s3.get_bucket_location(**kwargs)["LocationConstraint"] != REGION:
            raise RuntimeError("Monitored bucket is outside the staging AWS region")
        if s3.get_bucket_versioning(**kwargs).get("Status") != "Enabled":
            raise RuntimeError("The staging bucket should have versioning enabled")
        block = s3.get_public_access_block(**kwargs)["PublicAccessBlockConfiguration"]
        if len(block) != 4 or not all(block.values()):
            raise RuntimeError("The staging bucket does not block public access")
        config = notification_configuration(s3, bucket)
        print(f"{bucket}: existing EventBridge={'EventBridgeConfiguration' in config}", flush=True)
    sns = session.client("sns")
    subscriptions = [
        item
        for page in sns.get_paginator("list_subscriptions_by_topic").paginate(TopicArn=TOPIC)
        for item in page["Subscriptions"]
    ]
    if len(subscriptions) != 1:
        raise RuntimeError("Expected only the existing Academy operator subscription on the monitoring topic")
    subscription = subscriptions[0]
    if subscription["Protocol"] != "email" or not subscription["SubscriptionArn"].startswith(TOPIC + ":"):
        raise RuntimeError("The existing operator email subscription is not confirmed")
    attributes = sns.get_subscription_attributes(SubscriptionArn=subscription["SubscriptionArn"])["Attributes"]
    if attributes.get("FilterPolicy", "{}").strip() not in ("{}", ""):
        raise RuntimeError("The existing email subscription filters messages")
    print("Verified private staging buckets and a single confirmed operator email subscription.", flush=True)
    return s3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["preflight", "enable"])
    args = parser.parse_args()
    s3 = preflight(boto3.Session(region_name=REGION))
    if args.operation == "enable":
        changed = [bucket for bucket in (ARCHIVE, MEDIA) if enable_eventbridge(s3, bucket)]
        for bucket in changed:
            print(f"Enabled EventBridge for {bucket}, preserving its other notifications.", flush=True)
        if changed:
            print("Waiting five minutes for the S3 EventBridge settings to propagate.", flush=True)
            time.sleep(305)


if __name__ == "__main__":
    main()
