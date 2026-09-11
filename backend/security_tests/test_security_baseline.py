from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient


class SecurityBaselineTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_production_security_settings(self):
        """Assert the effective settings loaded by the production-like CI job."""
        if settings.DEBUG:
            self.skipTest("Production security assertions run in django-deploy-check with DEBUG=False.")
        self.assertTrue(settings.SECURE_SSL_REDIRECT)
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertGreaterEqual(settings.SECURE_HSTS_SECONDS, 31536000)
        self.assertTrue(settings.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(settings.SECURE_HSTS_PRELOAD)

    def test_cors_credentials_disabled(self):
        self.assertFalse(settings.CORS_ALLOW_CREDENTIALS)

    def test_rest_framework_throttling_configured(self):
        self.assertIn("DEFAULT_THROTTLE_CLASSES", settings.REST_FRAMEWORK)
        self.assertIn("DEFAULT_THROTTLE_RATES", settings.REST_FRAMEWORK)
        self.assertIn("anon", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])
        self.assertIn("user", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])

    def test_default_permissions_are_audited(self):
        # Public content APIs currently rely on AllowAny. Any future private API
        # must explicitly set a stricter permission class and be covered by
        # authorization/IDOR regression tests before production release.
        self.assertEqual(
            settings.REST_FRAMEWORK.get("DEFAULT_PERMISSION_CLASSES"),
            ["rest_framework.permissions.AllowAny"],
        )
