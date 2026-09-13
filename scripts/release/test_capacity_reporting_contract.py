import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "production-readiness" / "report.md"


class CapacityReportingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = REPORT.read_text(encoding="utf-8")

    def _field(self, label: str) -> str:
        match = re.search(
            rf"^\*\*{re.escape(label)}:\*\*\s+\*\*(.+?)\*\*\s*$",
            self.report,
            re.MULTILINE,
        )
        self.assertIsNotNone(match, f"Missing capacity report field: {label}")
        return match.group(1).strip()

    def test_required_capacity_fields_are_reported_independently(self):
        required = (
            "PRODUCTION READINESS",
            "MAXIMUM VERIFIED CONCURRENT USERS",
            "50,000 CONCURRENT USERS VERIFIED",
            "CAPACITY TEST ENVIRONMENT",
            "TEST TOOL",
            "TEST DURATION",
            "PEAK VERIFIED REQUEST RATE",
            "P95 RESPONSE TIME",
            "P99 RESPONSE TIME",
            "ERROR RATE",
            "CAPACITY EVIDENCE",
        )
        for label in required:
            self._field(label)

        self.assertIn(self._field("PRODUCTION READINESS"), {"PASS", "FAIL"})
        self.assertIn(self._field("50,000 CONCURRENT USERS VERIFIED"), {"YES", "NO"})

    def test_50k_yes_requires_at_least_50000_verified_users_and_real_evidence(self):
        max_users_text = self._field("MAXIMUM VERIFIED CONCURRENT USERS").replace(",", "")
        self.assertRegex(max_users_text, r"^\d+$")
        max_users = int(max_users_text)
        verified_50k = self._field("50,000 CONCURRENT USERS VERIFIED")

        if max_users < 50_000:
            self.assertEqual(verified_50k, "NO")

        if verified_50k == "YES":
            self.assertGreaterEqual(max_users, 50_000)
            placeholders = {"NOT EXECUTED", "NOT AVAILABLE", "NONE", "N/A"}
            for label in (
                "CAPACITY TEST ENVIRONMENT",
                "TEST TOOL",
                "TEST DURATION",
                "PEAK VERIFIED REQUEST RATE",
                "P95 RESPONSE TIME",
                "P99 RESPONSE TIME",
                "ERROR RATE",
                "CAPACITY EVIDENCE",
            ):
                self.assertNotIn(self._field(label).upper(), placeholders)

    def test_zero_is_only_a_no-test_sentinel_not_a_capacity_claim(self):
        max_users = int(self._field("MAXIMUM VERIFIED CONCURRENT USERS").replace(",", ""))
        if max_users == 0:
            self.assertEqual(self._field("50,000 CONCURRENT USERS VERIFIED"), "NO")
            self.assertRegex(
                self.report.lower(),
                r"no controlled (?:concurrency|capacity|load).*test.*completed|no controlled.*test.*completed",
            )


if __name__ == "__main__":
    unittest.main()
