import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


@unittest.skipUnless(importlib.util.find_spec("locust"), "Locust is installed by the load-test workflow")
class RuntimeSafetyTests(unittest.TestCase):
    def test_no_request_can_run_before_or_after_failed_preflight(self):
        from load_tests import locustfile as runner

        environment = SimpleNamespace(runner=Mock(), process_exit_code=None)
        with patch.object(runner, "SAFETY_PASSED", False):
            with patch.object(runner, "validate_safety", side_effect=ValueError("private details")):
                with self.assertRaises(RuntimeError) as error:
                    runner.validate_run(environment)
            self.assertNotIn("private details", str(error.exception))
            environment.runner.quit.assert_called_once()
            self.assertEqual(environment.process_exit_code, 2)
            user = Mock()
            with self.assertRaises(runner.StopUser):
                runner.checked_get(user, "/", "homepage")
            with self.assertRaises(runner.StopUser):
                runner.checked_post(user, "/checkout", "checkout", {})
            user.client.get.assert_not_called()
            user.client.post.assert_not_called()

    def test_checked_reads_never_follow_redirects(self):
        from load_tests import locustfile as runner

        user = Mock()
        response = Mock(status_code=302)
        user.client.get.return_value = unittest.mock.MagicMock()
        user.client.get.return_value.__enter__.return_value = response
        with patch.object(runner, "SAFETY_PASSED", True):
            runner.checked_get(user, "/", "homepage")
        self.assertFalse(user.client.get.call_args.kwargs["allow_redirects"])
