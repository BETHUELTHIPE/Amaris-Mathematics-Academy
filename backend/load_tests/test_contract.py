import os
import unittest
from unittest.mock import patch

from load_tests.config import Endpoints, missing_full_journey_configuration, validate_target


class LoadTestSafetyTests(unittest.TestCase):
    def test_live_amaris_site_is_blocked_without_authorisation(self):
        with self.assertRaisesRegex(ValueError, "live Amaris Site"):
            validate_target(
                "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site",
                environment_name="production",
                allowed_hosts=(),
                allow_production=False,
                allow_live_payfast=False,
            )

    def test_payfast_is_blocked_without_explicit_authorisation(self):
        with self.assertRaisesRegex(ValueError, "PayFast"):
            validate_target(
                "https://www.payfast.co.za",
                environment_name="staging",
                allowed_hosts=(),
                allow_production=False,
                allow_live_payfast=False,
            )

    def test_target_must_be_explicitly_allowed(self):
        with self.assertRaisesRegex(ValueError, "LOADTEST_ALLOWED_HOSTS"):
            validate_target(
                "https://staging.example.com",
                environment_name="staging",
                allowed_hosts=("approved.example.com",),
                allow_production=False,
                allow_live_payfast=False,
            )

    def test_external_endpoint_paths_are_rejected(self):
        with patch.dict(os.environ, {"LOADTEST_CHECKOUT_PATH": "https://www.payfast.co.za/eng/process"}, clear=True):
            with self.assertRaisesRegex(ValueError, "relative application path"):
                Endpoints.from_environment()

    def test_full_journey_lists_unconfigured_writes_and_protected_routes(self):
        missing = missing_full_journey_configuration(Endpoints())
        self.assertIn("LOADTEST_LESSON_PATH", missing)
        self.assertIn("LOADTEST_CHECKOUT_PATH", missing)
        self.assertIn("LOADTEST_PAYMENT_STATUS_PATH", missing)


if __name__ == "__main__":
    unittest.main()
