import os
import unittest
from pathlib import Path
from unittest.mock import patch

from load_tests.capacity import (
    CAPACITY_LEVELS,
    CapacityThresholds,
    progressive_levels,
    validate_capacity_level,
)
from load_tests.config import (
    Endpoints,
    missing_full_journey_configuration,
    validate_target,
)


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
        with patch.dict(
            os.environ,
            {"LOADTEST_CHECKOUT_PATH": "https://www.payfast.co.za/eng/process"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "relative application path"):
                Endpoints.from_environment()

    def test_full_journey_lists_unconfigured_writes_and_protected_routes(self):
        missing = missing_full_journey_configuration(Endpoints())
        self.assertIn("LOADTEST_LESSON_PATH", missing)
        self.assertIn("LOADTEST_CHECKOUT_PATH", missing)
        self.assertIn("LOADTEST_PAYMENT_STATUS_PATH", missing)


class CapacityContractTests(unittest.TestCase):
    @staticmethod
    def _workflow_text() -> str:
        workflow = (
            Path(__file__).resolve().parents[2]
            / ".github"
            / "workflows"
            / "capacity.yml"
        )
        return workflow.read_text(encoding="utf-8")

    @staticmethod
    def _capacity_locust_text() -> str:
        path = Path(__file__).resolve().parent / "capacity_locustfile.py"
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _capacity_report_text() -> str:
        path = Path(__file__).resolve().parent / "capacity_report.py"
        return path.read_text(encoding="utf-8")

    def test_capacity_levels_are_exact_progressive_sequence(self):
        self.assertEqual(
            CAPACITY_LEVELS,
            (100, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000),
        )
        self.assertEqual(
            progressive_levels(5_000),
            (100, 500, 1_000, 2_500, 5_000),
        )

    def test_unapproved_capacity_level_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported capacity level"):
            validate_capacity_level(49_999)

    def test_capacity_thresholds_match_or_exceed_normal_release_gate(self):
        with patch.dict(os.environ, {}, clear=True):
            thresholds = CapacityThresholds.from_environment()
        self.assertEqual(thresholds.failure_pct, 1.0)
        self.assertEqual(thresholds.server_5xx_pct, 0.1)
        self.assertEqual(thresholds.p95_ms, 1_000)
        self.assertEqual(thresholds.p99_ms, 2_000)
        self.assertEqual(thresholds.infrastructure_cpu_pct, 90.0)
        self.assertEqual(thresholds.infrastructure_ram_pct, 90.0)

    def test_capacity_thresholds_cannot_be_weakened_by_environment(self):
        weaker_values = {
            "CAPACITY_MAX_FAILURE_PCT": "1.01",
            "CAPACITY_MAX_5XX_PCT": "0.11",
            "CAPACITY_MAX_P95_MS": "1001",
            "CAPACITY_MAX_P99_MS": "2001",
            "CAPACITY_MAX_CPU_PCT": "90.1",
            "CAPACITY_MAX_RAM_PCT": "90.1",
        }
        for name, value in weaker_values.items():
            with (
                self.subTest(name=name),
                patch.dict(os.environ, {name: value}, clear=True),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "would weaken the capacity gate",
                ):
                    CapacityThresholds.from_environment()

    def test_stricter_capacity_thresholds_are_allowed(self):
        with patch.dict(
            os.environ,
            {
                "CAPACITY_MAX_FAILURE_PCT": "0.5",
                "CAPACITY_MAX_5XX_PCT": "0.05",
                "CAPACITY_MAX_P95_MS": "800",
                "CAPACITY_MAX_P99_MS": "1500",
                "CAPACITY_MAX_CPU_PCT": "85",
                "CAPACITY_MAX_RAM_PCT": "85",
            },
            clear=True,
        ):
            thresholds = CapacityThresholds.from_environment()
        self.assertEqual(thresholds.failure_pct, 0.5)
        self.assertEqual(thresholds.server_5xx_pct, 0.05)
        self.assertEqual(thresholds.p95_ms, 800)
        self.assertEqual(thresholds.p99_ms, 1_500)
        self.assertEqual(thresholds.infrastructure_cpu_pct, 85.0)
        self.assertEqual(thresholds.infrastructure_ram_pct, 85.0)

    def test_capacity_workflow_is_manual_only(self):
        text = self._workflow_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("push:", text)
        self.assertNotIn("schedule:", text)

    def test_capacity_workflow_contains_every_required_stage(self):
        text = self._workflow_text()
        self.assertIn(
            "stages=(100 500 1000 2500 5000 10000 25000 50000)",
            text,
        )
        self.assertIn("50,000 CONCURRENT USERS VERIFIED:** NO", text)

    def test_capacity_workflow_blocks_production_and_requires_dedicated_generator(
        self,
    ):
        text = self._workflow_text()
        self.assertIn('LOADTEST_ALLOW_PRODUCTION: "false"', text)
        self.assertNotIn("allow_production:", text)
        self.assertIn(
            "Capacity stages above 1,000 users require a dedicated "
            "self-hosted load generator.",
            text,
        )
        self.assertIn("inputs.load_generator == 'self-hosted'", text)
        self.assertIn("capacity-load-generator", text)

    def test_capacity_workflow_requires_immutable_target_identity(self):
        text = self._workflow_text()
        self.assertIn("CAPACITY_TARGET_GIT_SHA", text)
        self.assertIn("CAPACITY_TARGET_IMAGE", text)
        self.assertIn("40-character Git SHA", text)
        self.assertIn(":latest is not accepted", text)

    def test_capacity_report_records_reproducible_provenance(self):
        text = self._capacity_report_text()
        self.assertIn('"target_git_sha"', text)
        self.assertIn('"target_image"', text)
        self.assertIn('"capacity_harness_git_sha"', text)
        self.assertIn('"locust_version"', text)
        self.assertIn('"tested_at_utc"', text)

    def test_capacity_requires_sustained_hold_and_fast_http_users(self):
        text = self._capacity_locust_text()
        self.assertIn("FastHttpUser", text)
        self.assertIn("target_hold_seconds_observed", text)
        self.assertIn("target_hold_sustained", text)
        self.assertIn("HOLD_SECONDS - 15.0", text)


if __name__ == "__main__":
    unittest.main()
