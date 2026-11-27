"""Check retry behavior, event filtering and existing notification preservation."""

import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml
from botocore.exceptions import ClientError

from configure import (ACCOUNT, ARCHIVE, MEDIA, REGION, TOPIC, NOTIFICATION_ID,
                       S3_EVENTS, enable_notifications)
from verify import event_for


class CloudFormationLoader(yaml.SafeLoader):
    pass


def load_intrinsic(loader, tag, node):
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)


CloudFormationLoader.add_multi_constructor("!", load_intrinsic)


def direct_notification(bucket, name, key):
    return {"Records": [{
        "eventSource": "aws:s3", "awsRegion": REGION, "eventName": name,
        "eventTime": "2026-01-01T00:00:00Z",
        "s3": {"bucket": {"name": bucket, "arn": "arn:aws:s3:::" + bucket},
               "object": {"key": key, "versionId": "version"}},
        "responseElements": {"x-amz-request-id": "request-id"},
    }]}


class AlertsTest(unittest.TestCase):
    def setUp(self):
        template = yaml.load(Path(__file__).with_name("stack.yml").read_text(), Loader=CloudFormationLoader)
        code = template["Resources"]["NotifyOperator"]["Properties"]["Code"]["ZipFile"]
        self.sns = Mock()
        self.sns.publish.return_value = {"MessageId": "sns-receipt"}
        self.function = {}
        settings = {"BUCKETS": f"{MEDIA},{ARCHIVE}", "AWS_REGION": REGION, "ACCOUNT": ACCOUNT, "TOPIC_ARN": TOPIC}
        self.environment = patch.dict(os.environ, settings)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        with patch("boto3.client", return_value=self.sns):
            exec(compile(code, "stack.yml/NotifyOperator", "exec"), self.function)

    def invoke(self, *events):
        records = [{"messageId": str(index), "body": json.dumps(event)} for index, event in enumerate(events)]
        with patch("builtins.print") as log:
            response = self.function["handler"]({"Records": records}, None)
        return response, [json.loads(call.args[0]) for call in log.call_args_list]

    def test_batches_valid_events_and_rejects_an_unrelated_bucket(self):
        tag = direct_notification(MEDIA, "ObjectTagging:Put", "lesson%2Fspace+%2B+newline%0A.mp4")
        deletion = direct_notification(ARCHIVE, "ObjectRemoved:Delete", "archive%2Ftest.log")
        denied = direct_notification("another-bucket", "ObjectCreated:Put", "outside.txt")
        response, logged = self.invoke(tag, tag, deletion, denied)
        self.assertEqual(response, {"batchItemFailures": [{"itemIdentifier": "3"}]})
        self.sns.publish.assert_called_once()
        self.assertEqual(self.sns.publish.call_args.kwargs["TopicArn"], TOPIC)
        lines = self.sns.publish.call_args.kwargs["Message"].splitlines()[2:]
        self.assertEqual(len(lines), 2)
        key = "lesson/space + newline\n.mp4"
        self.assertEqual(json.loads(lines[0])["key"], key)
        self.assertEqual(json.loads(lines[1])["reason"], "ObjectRemoved:Delete")
        self.assertEqual(logged[1]["key_sha256"], hashlib.sha256(key.encode()).hexdigest())
        self.assertEqual(logged[1]["sns_message_id"], "sns-receipt")
        self.assertNotIn("key", logged[1])

    def test_sns_failure_retries_accepted_queue_records(self):
        self.sns.publish.side_effect = ClientError({"Error": {"Code": "Throttled"}}, "Publish")
        result, log = self.invoke(direct_notification(MEDIA, "ObjectCreated:Put", "test"), event_for(ARCHIVE, "Async Copy Completion"))
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "0"}, {"itemIdentifier": "1"}]})
        self.assertEqual(log, [{"status": "publish_failed", "error_type": "ClientError"}])

    def test_cloudtrail_and_wrong_account_do_not_send_email(self):
        wrong_account = event_for(MEDIA, "Async Copy Completion")
        wrong_account["account"] = "012345678901"
        response, _ = self.invoke(event_for(MEDIA, "AWS API Call via CloudTrail"), wrong_account)
        self.assertEqual(response, {"batchItemFailures": [{"itemIdentifier": "0"}, {"itemIdentifier": "1"}]})
        self.sns.publish.assert_not_called()


    def test_bucket_validation_event_does_not_email(self):
        response, _ = self.invoke({"Event": "s3:TestEvent", "Service": "Amazon S3", "Bucket": MEDIA})
        self.assertEqual(response, {"batchItemFailures": []})
        self.sns.publish.assert_not_called()


class ConfigurationTest(unittest.TestCase):
    def test_bucket_configuration_preserves_an_existing_lambda_notification(self):
        s3 = Mock()
        existing = {"LambdaFunctionConfigurations": [{"Id": "already-configured", "Events": ["s3:ObjectCreated:Put"]}]}
        queue_arn = f"arn:aws:sqs:{REGION}:{ACCOUNT}:test"
        queue = {"Id": NOTIFICATION_ID, "QueueArn": queue_arn, "Events": S3_EVENTS}
        updated = {**existing, "EventBridgeConfiguration": {}, "QueueConfigurations": [queue]}
        reordered = {**updated, "QueueConfigurations": [{**queue, "Events": S3_EVENTS[::-1]}]}
        s3.get_bucket_notification_configuration.side_effect = [dict(existing), dict(reordered), dict(reordered)]
        self.assertTrue(enable_notifications(s3, MEDIA, queue_arn))
        self.assertFalse(enable_notifications(s3, MEDIA, queue_arn))
        s3.put_bucket_notification_configuration.assert_called_once_with(
            Bucket=MEDIA, ExpectedBucketOwner=ACCOUNT, NotificationConfiguration=updated
        )
