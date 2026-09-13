from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "release" / "post-deploy-smoke.sh"
PROMOTE_SCRIPT = REPO_ROOT / "scripts" / "release" / "promote.sh"


class PostDeploySmokeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")
        cls.promote = PROMOTE_SCRIPT.read_text(encoding="utf-8")

    def test_required_safe_routes_are_covered(self):
        for expected in (
            '"${APPLICATION_URL%/}/"',
            '"${APPLICATION_URL%/}/login"',
            '"${APPLICATION_URL%/}/courses"',
            '"$HEALTHCHECK_URL"',
            '"$API_HEALTH_URL"',
        ):
            self.assertIn(expected, self.smoke)

    def test_static_asset_is_discovered_and_verified(self):
        self.assertIn("_next/static", self.smoke)
        self.assertIn('request "static asset" "$asset_url"', self.smoke)

    def test_smoke_checks_are_read_only(self):
        for unsafe_method in ("--request POST", "--request PUT", "--request PATCH", "--request DELETE"):
            self.assertNotIn(unsafe_method, self.smoke)
        self.assertNotIn("/checkout", self.smoke)
        self.assertNotIn("/payment", self.smoke)
        self.assertNotIn("payfast", self.smoke.lower())

    def test_https_is_mandatory(self):
        self.assertIn("require_https", self.smoke)
        self.assertIn("--proto '=https'", self.smoke)
        self.assertIn("--tlsv1.2", self.smoke)

    def test_production_promotion_runs_smoke_before_success(self):
        smoke_index = self.promote.index("scripts/release/post-deploy-smoke.sh")
        success_index = self.promote.index('write_record "succeeded"')
        self.assertLess(smoke_index, success_index)
        self.assertIn('if [ "$environment_name" = "production" ]; then', self.promote)

    def test_failed_smoke_causes_rollback_path(self):
        self.assertIn("failed critical health or post-deploy checks", self.promote)
        self.assertIn('deploy-webhook.sh rollback "$environment_name" "$previous_image"', self.promote)
        self.assertIn('write_record "rolled-back"', self.promote)


if __name__ == "__main__":
    unittest.main()
