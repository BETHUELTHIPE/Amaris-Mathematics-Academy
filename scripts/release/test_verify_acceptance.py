import unittest
from datetime import UTC, datetime

from verify_acceptance import REQUIRED_IDS, validate_manifest


def accepted_manifest():
    verified_at = datetime.now(UTC).isoformat()
    return {
        "release_status": "accepted",
        "criteria": [
            {
                "id": criterion_id,
                "name": f"Criterion {criterion_id}",
                "status": "passed",
                "evidence": ["artifact://approved-evidence"],
                "verified_by": "release-reviewer@example.invalid",
                "verified_at": verified_at,
            }
            for criterion_id in sorted(REQUIRED_IDS)
        ],
    }


class AcceptanceGateTests(unittest.TestCase):
    def test_complete_approved_manifest_passes(self):
        self.assertEqual(validate_manifest(accepted_manifest()), [])

    def test_pending_or_unevidenced_criterion_blocks_release(self):
        manifest = accepted_manifest()
        manifest["criteria"][7]["status"] = "partial"
        manifest["criteria"][7]["evidence"] = []

        errors = validate_manifest(manifest)

        self.assertIn("criterion 8 is not passed", errors)
        self.assertIn("criterion 8 has no evidence", errors)

    def test_missing_criterion_blocks_release(self):
        manifest = accepted_manifest()
        manifest["criteria"].pop()

        self.assertIn("criterion 20 is missing", validate_manifest(manifest))


if __name__ == "__main__":
    unittest.main()
