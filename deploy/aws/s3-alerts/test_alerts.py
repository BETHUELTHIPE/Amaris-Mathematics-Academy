"""Check retry behavior, event filtering and existing notification preservation."""

import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml
from botocore.exceptions import ClientError

from configure import ACCOUNT, ARCHIVE, MEDIA, REGION, TOPIC, enable_eventbridge
from verify import event_for


class CloudFormationLoader(yaml.SafeLoader):
    pass


def load_intrinsic(loader, tag, node):
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)


CloudFormationLoader.add_multi_constructor("!", load_intrinsic)


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
        tag = event_for(MEDIA, "Object Tags Added")
        tag["detail"]["object"]["key"] = "lesson/space + newline\n.mp4"
        deletion = event_for(ARCHIVE, "Object Deleted")
        deletion["detail"]["deletion-type"] = "Permanently Deleted"
        denied = event_for("another-bucket", "Object Created")
        response, logged = self.invoke(tag, tag, deletion, denied)
        self.assertEqual(response, {"batchItemFailures": [{"itemIdentifier": "3"}]})
        self.sns.publish.assert_called_once()
        self.assertEqual(self.sns.publish.call_args.kwargs["TopicArn"], TOPIC)
        lines = self.sns.publish.call_args.kwargs["Message"].splitlines()[2:]
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["key"], tag["detail"]["object"]["key"])
        self.assertEqual(json.loads(lines[1])["deletion_type"], "Permanently Deleted")
        self.assertEqual(logged[1]["key_sha256"], hashlib.sha256(tag["detail"]["object"]["key"].encode()).hexdigest())
        self.assertEqual(logged[1]["sns_message_id"], "sns-receipt")
        self.assertNotIn("key", logged[1])

    def test_sns_failure_retries_accepted_queue_records(self):
        self.sns.publish.side_effect = ClientError({"Error": {"Code": "Throttled"}}, "Publish")
        result, log = self.invoke(event_for(MEDIA, "Object Created"), event_for(ARCHIVE, "Object Storage Class Changed"))
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "0"}, {"itemIdentifier": "1"}]})
        self.assertEqual(log, [{"status": "publish_failed", "error_type": "ClientError"}])

    def test_cloudtrail_and_wrong_account_do_not_send_email(self):
        wrong_account = event_for(MEDIA, "Object Deleted")
        wrong_account["account"] = "012345678901"
        response, _ = self.invoke(event_for(MEDIA, "AWS API Call via CloudTrail"), wrong_account)
        self.assertEqual(response, {"batchItemFailures": [{"itemIdentifier": "0"}, {"itemIdentifier": "1"}]})
        self.sns.publish.assert_not_called()


class ConfigurationTest(unittest.TestCase):
    def test_bucket_configuration_preserves_an_existing_lambda_notification(self):
        s3 = Mock()
        existing = {"LambdaFunctionConfigurations": [{"Id": "already-configured"}]}
        updated = {**existing, "EventBridgeConfiguration": {}}
        s3.get_bucket_notification_configuration.side_effect = [dict(existing), dict(updated), dict(updated)]
        self.assertTrue(enable_eventbridge(s3, MEDIA))
        self.assertFalse(enable_eventbridge(s3, MEDIA))
        s3.put_bucket_notification_configuration.assert_called_once_with(
            Bucket=MEDIA, ExpectedBucketOwner=ACCOUNT, NotificationConfiguration=updated
        )
