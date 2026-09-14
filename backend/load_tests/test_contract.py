import os
import unittest
from pathlib import Path
from unittest.mock import patch

from load_tests.capacity import CAPACITY_LEVELS, CapacityThresholds, progressive_levels, validate_capacity_level
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


class CapacityContractTests(unittest.TestCase):
    def test_capacity_levels_are_exact_progressive_sequence(self):
        self.assertEqual(CAPACITY_LEVELS, (100, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000))
        self.assertEqual(progressive_levels(5_000), (100, 500, 1_000, 2_500, 5_000))

    def test_unapproved_capacity_level_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported capacity level"):
            validate_capacity_level(49_999)

    def test_capacity_thresholds_are_not_silently_weakened(self):
        with patch.dict(os.environ, {}, clear=True):
            thresholds = CapacityThresholds.from_environment()
        self.assertEqual(thresholds.failure_pct, 1.0)
        self.assertEqual(thresholds.server_5xx_pct, 0.5)
        self.assertEqual(thresholds.p95_ms, 2_000)
        self.assertEqual(thresholds.p99_ms, 4_000)
        self.assertEqual(thresholds.infrastructure_cpu_pct, 90.0)
        self.assertEqual(thresholds.infrastructure_ram_pct, 90.0)

    def test_capacity_workflow_is_manual_only(self):
        workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "capacity.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("push:", text)
        self.assertNotIn("schedule:", text)

    def test_capacity_workflow_contains_every_required_stage(self):
        workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "capacity.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("stages=(100 500 1000 2500 5000 10000 25000 50000)", text)
        self.assertIn("50,000 CONCURRENT USERS VERIFIED:** NO", text)


if __name__ == "__main__":
    unittest.main()
