from django.conf import settings
from django.test import SimpleTestCase

from amaris_cms import settings as project_settings


class DualStorageConfigurationTests(SimpleTestCase):
    def test_cms_and_student_storage_aliases_exist(self):
        self.assertIn("cms", settings.STORAGES)
        self.assertIn("student_data", settings.STORAGES)

    def test_default_storage_routes_to_cms_storage(self):
        self.assertEqual(settings.STORAGES["default"], settings.STORAGES["cms"])

    def test_cms_and_student_storage_are_separate(self):
        cms_options = settings.STORAGES["cms"].get("OPTIONS", {})
        student_options = settings.STORAGES["student_data"].get("OPTIONS", {})

        cms_target = cms_options.get("bucket_name") or cms_options.get("location")
        student_target = student_options.get("bucket_name") or student_options.get("location")

        self.assertTrue(cms_target)
        self.assertTrue(student_target)
        self.assertNotEqual(cms_target, student_target)

    def test_s3_storage_uses_private_signed_urls_and_path_style(self):
        config = project_settings._s3_storage("example-private-bucket")
        options = config["OPTIONS"]

        self.assertEqual(config["BACKEND"], "storages.backends.s3.S3Storage")
        self.assertEqual(options["bucket_name"], "example-private-bucket")
        self.assertIsNone(options["default_acl"])
        self.assertTrue(options["querystring_auth"])
        self.assertFalse(options["file_overwrite"])
        self.assertEqual(options["addressing_style"], project_settings.SUPABASE_S3_ADDRESSING_STYLE)

    def test_supabase_endpoint_is_applied_when_configured(self):
        config = project_settings._s3_storage("example-private-bucket")
        endpoint = project_settings.SUPABASE_S3_ENDPOINT_URL

        if endpoint:
            self.assertEqual(config["OPTIONS"]["endpoint_url"], endpoint)
        else:
            self.assertNotIn("endpoint_url", config["OPTIONS"])
