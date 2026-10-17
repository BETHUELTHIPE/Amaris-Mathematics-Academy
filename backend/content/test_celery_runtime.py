"""Mock-only tests for the *real* staging Celery runtime probe command.

The staging command must additionally be executed inside the deployed environment;
these CI tests do not claim that live workers are healthy.
"""

from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class CeleryRuntimeVerificationTests(SimpleTestCase):
    @patch("content.management.commands.verify_celery_runtime.app")
    def test_each_queue_requires_a_real_worker_response(self, celery_app):
        celery_app.conf.task_always_eager = False
        celery_app.conf.result_backend = "redis://example.invalid/1"
        results = []

        def enqueue(name, *, args, queue, expires, ignore_result):
            self.assertEqual(name, "content.tasks.runtime_worker_probe")
            self.assertTrue(ignore_result is False)
            self.assertGreaterEqual(expires, 30)
            result = Mock()
            result.get.return_value = {"nonce": args[0], "queue": queue}
            results.append(result)
            return result

        celery_app.send_task.side_effect = enqueue
        output = StringIO()
        call_command("verify_celery_runtime", stdout=output)
        self.assertEqual(
            [call.kwargs["queue"] for call in celery_app.send_task.call_args_list],
            ["critical", "default", "notifications"],
        )
        self.assertEqual(len(results), 3)
        for result in results:
            result.forget.assert_called_once_with()
        self.assertEqual(output.getvalue().count("PASS"), 3)

    @patch("content.management.commands.verify_celery_runtime.app")
    def test_eager_mode_cannot_be_misreported_as_staging_success(self, celery_app):
        celery_app.conf.task_always_eager = True
        celery_app.conf.result_backend = "redis://example.invalid/1"
        with self.assertRaisesMessage(CommandError, "Eager Celery mode"):
            call_command("verify_celery_runtime")
        celery_app.send_task.assert_not_called()

    @patch("content.management.commands.verify_celery_runtime.app")
    def test_mismatched_queue_is_a_hard_failure(self, celery_app):
        celery_app.conf.task_always_eager = False
        celery_app.conf.result_backend = "redis://example.invalid/1"
        result = Mock()
        result.get.return_value = {"nonce": "wrong", "queue": "default"}
        celery_app.send_task.return_value = result
        with self.assertRaisesMessage(CommandError, "unexpected worker response"):
            call_command("verify_celery_runtime")
        result.forget.assert_not_called()

    @patch("content.management.commands.verify_celery_runtime.app")
    def test_broker_failure_fails_closed_without_printing_error(self, celery_app):
        celery_app.conf.task_always_eager = False
        celery_app.conf.result_backend = "redis://example.invalid/1"
        celery_app.send_task.side_effect = RuntimeError("sensitive connection string")
        with self.assertRaisesMessage(CommandError, "real worker execution failed") as caught:
            call_command("verify_celery_runtime")
        self.assertNotIn("sensitive", str(caught.exception))

    def test_invalid_timeout_is_rejected(self):
        with self.assertRaisesMessage(CommandError, "Timeout must be"):
            call_command("verify_celery_runtime", timeout=0)
