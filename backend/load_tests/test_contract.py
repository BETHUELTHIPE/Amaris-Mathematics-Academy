import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from load_tests.capacity_evidence import build_capacity_evidence, configured_peak_users
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


class CapacityEvidenceTests(unittest.TestCase):
    def write_csv(
        self, path: Path, fieldnames: list[str], rows: list[dict[str, object]]
    ) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_configured_peak_is_not_automatically_verified(self):
        self.assertEqual(configured_peak_users("spike"), 200)
        with tempfile.TemporaryDirectory() as directory:
            evidence = build_capacity_evidence(
                profile="spike",
                exit_code=0,
                environment_name="staging",
                results_dir=Path(directory),
                run_reference="test-run",
            )

        self.assertEqual(evidence["configured_peak_users"], 200)
        self.assertEqual(evidence["maximum_verified_concurrent_users"], 0)
        self.assertFalse(evidence["fifty_thousand_concurrent_users_verified"])

    def test_successful_run_uses_observed_users_not_configured_users(self):
        with tempfile.TemporaryDirectory() as directory:
            results_dir = Path(directory)
            self.write_csv(
                results_dir / "spike_stats_history.csv",
                ["Timestamp", "Name", "User Count", "Requests/s"],
                [
                    {
                        "Timestamp": 1000,
                        "Name": "Aggregated",
                        "User Count": 20,
                        "Requests/s": 12.5,
                    },
                    {
                        "Timestamp": 1030,
                        "Name": "Aggregated",
                        "User Count": 180,
                        "Requests/s": 220.0,
                    },
                ],
            )
            self.write_csv(
                results_dir / "spike_stats.csv",
                ["Name", "Request Count", "Failure Count", "95%", "99%"],
                [
                    {
                        "Name": "Aggregated",
                        "Request Count": 10000,
                        "Failure Count": 10,
                        "95%": 850,
                        "99%": 1400,
                    }
                ],
            )
            evidence = build_capacity_evidence(
                profile="spike",
                exit_code=0,
                environment_name="staging",
                results_dir=results_dir,
                run_reference="test-run",
            )

        self.assertEqual(evidence["configured_peak_users"], 200)
        self.assertEqual(evidence["maximum_verified_concurrent_users"], 180)
        self.assertFalse(evidence["fifty_thousand_concurrent_users_verified"])
        self.assertAlmostEqual(evidence["error_rate"], 0.001)

    def test_failed_run_never_verifies_50000_users(self):
        with tempfile.TemporaryDirectory() as directory:
            results_dir = Path(directory)
            self.write_csv(
                results_dir / "spike_stats_history.csv",
                ["Timestamp", "Name", "User Count", "Requests/s"],
                [
                    {
                        "Timestamp": 1000,
                        "Name": "Aggregated",
                        "User Count": 50000,
                        "Requests/s": 5000,
                    }
                ],
            )
            evidence = build_capacity_evidence(
                profile="spike",
                exit_code=1,
                environment_name="staging",
                results_dir=results_dir,
                run_reference="failed-run",
            )

        self.assertEqual(evidence["maximum_verified_concurrent_users"], 0)
        self.assertFalse(evidence["fifty_thousand_concurrent_users_verified"])

    def test_50000_requires_successful_observed_50000_users(self):
        with tempfile.TemporaryDirectory() as directory:
            results_dir = Path(directory)
            self.write_csv(
                results_dir / "spike_stats_history.csv",
                ["Timestamp", "Name", "User Count", "Requests/s"],
                [
                    {
                        "Timestamp": 1000,
                        "Name": "Aggregated",
                        "User Count": 50000,
                        "Requests/s": 5000,
                    }
                ],
            )
            evidence = build_capacity_evidence(
                profile="spike",
                exit_code=0,
                environment_name="staging",
                results_dir=results_dir,
                run_reference="controlled-capacity-test",
            )

        self.assertEqual(evidence["maximum_verified_concurrent_users"], 50000)
        self.assertTrue(evidence["fifty_thousand_concurrent_users_verified"])


if __name__ == "__main__":
    unittest.main()
