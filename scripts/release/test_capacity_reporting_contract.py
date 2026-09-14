import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "production-readiness" / "report.md"

PLACEHOLDERS = {"NOT EXECUTED", "NOT AVAILABLE", "NONE", "N/A", "NOT ESTABLISHED"}
EVIDENCE_FIELDS = (
    "CAPACITY TEST ENVIRONMENT",
    "TEST TOOL",
    "TEST DURATION",
    "PEAK VERIFIED REQUEST RATE",
    "P95 RESPONSE TIME",
    "P99 RESPONSE TIME",
    "ERROR RATE",
    "CAPACITY EVIDENCE",
)


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

    def _maximum_verified_users(self) -> int | None:
        value = self._field("MAXIMUM VERIFIED CONCURRENT USERS").replace(",", "")
        if value.upper() == "NOT ESTABLISHED":
            return None
        self.assertRegex(
            value,
            r"^\d+$",
            "Maximum verified concurrent users must be an actual tested integer or NOT ESTABLISHED.",
        )
        return int(value)

    def test_required_capacity_fields_are_reported_independently(self):
        required = (
            "PRODUCTION READINESS",
            "MAXIMUM VERIFIED CONCURRENT USERS",
            "50,000 CONCURRENT USERS VERIFIED",
            *EVIDENCE_FIELDS,
        )
        for label in required:
            self._field(label)

        self.assertIn(self._field("PRODUCTION READINESS"), {"PASS", "FAIL"})
        self.assertIn(self._field("50,000 CONCURRENT USERS VERIFIED"), {"YES", "NO"})

    def test_no_capacity_test_means_no_fabricated_maximum(self):
        max_users = self._maximum_verified_users()
        if max_users is None:
            self.assertEqual(self._field("50,000 CONCURRENT USERS VERIFIED"), "NO")
            self.assertIn(self._field("CAPACITY TEST ENVIRONMENT").upper(), PLACEHOLDERS)
            self.assertIn(self._field("TEST TOOL").upper(), PLACEHOLDERS)
            self.assertIn(self._field("TEST DURATION").upper(), PLACEHOLDERS)
            self.assertIn(self._field("PEAK VERIFIED REQUEST RATE").upper(), PLACEHOLDERS)
            self.assertIn(self._field("P95 RESPONSE TIME").upper(), PLACEHOLDERS)
            self.assertIn(self._field("P99 RESPONSE TIME").upper(), PLACEHOLDERS)
            self.assertIn(self._field("ERROR RATE").upper(), PLACEHOLDERS)
            self.assertRegex(
                self.report.lower(),
                r"no completed controlled (?:concurrency|capacity|load).*test|no completed.*capacity.*test",
            )

    def test_any_positive_capacity_claim_requires_real_evidence(self):
        max_users = self._maximum_verified_users()
        if max_users is None:
            return

        self.assertGreater(
            max_users,
            0,
            "Do not use 0 as a synthetic capacity result; use NOT ESTABLISHED when no controlled test has passed.",
        )
        for label in EVIDENCE_FIELDS:
            self.assertNotIn(
                self._field(label).upper(),
                PLACEHOLDERS,
                f"{label} must contain retained test evidence for a positive capacity claim.",
            )

    def test_50k_yes_requires_at_least_50000_verified_users_and_real_evidence(self):
        max_users = self._maximum_verified_users()
        verified_50k = self._field("50,000 CONCURRENT USERS VERIFIED")

        if max_users is None or max_users < 50_000:
            self.assertEqual(verified_50k, "NO")

        if verified_50k == "YES":
            self.assertIsNotNone(max_users)
            self.assertGreaterEqual(max_users, 50_000)
            for label in EVIDENCE_FIELDS:
                self.assertNotIn(self._field(label).upper(), PLACEHOLDERS)


if __name__ == "__main__":
    unittest.main()
