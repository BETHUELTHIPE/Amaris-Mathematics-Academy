import csv
import tempfile
import unittest
from pathlib import Path

from load_tests.capacity_evidence import build_capacity_evidence, configured_peak_users


class CapacityEvidenceTests(unittest.TestCase):
    def write_csv(self, path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
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

    def test_successful_run_uses_observed_user_count_not_configured_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            results_dir = Path(directory)
            self.write_csv(
                results_dir / "spike_stats_history.csv",
                ["Timestamp", "User Count", "Requests/s"],
                [
                    {"Timestamp": 1000, "User Count": 20, "Requests/s": 12.5},
                    {"Timestamp": 1030, "User Count": 175, "Requests/s": 220.0},
                    {"Timestamp": 1060, "User Count": 180, "Requests/s": 215.0},
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
        self.assertEqual(evidence["observed_max_concurrent_users"], 180)
        self.assertEqual(evidence["maximum_verified_concurrent_users"], 180)
        self.assertFalse(evidence["fifty_thousand_concurrent_users_verified"])
        self.assertAlmostEqual(evidence["error_rate"], 0.001)

    def test_failed_run_never_verifies_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            results_dir = Path(directory)
            self.write_csv(
                results_dir / "spike_stats_history.csv",
                ["Timestamp", "User Count", "Requests/s"],
                [{"Timestamp": 1000, "User Count": 50000, "Requests/s": 1000}],
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
                ["Timestamp", "User Count", "Requests/s"],
                [{"Timestamp": 1000, "User Count": 50000, "Requests/s": 5000}],
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
