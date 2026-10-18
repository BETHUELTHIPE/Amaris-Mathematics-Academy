import unittest
from unittest.mock import MagicMock, patch

import activate_dedicated_staging as activation


class StagingActivationTests(unittest.TestCase):
    def test_rejects_production_connection_and_secret_key(self):
        with self.assertRaises(RuntimeError):
            activation.settings_for({"STAGING_DATABASE_URL": "postgresql://postgres:synthetic@db.epkcuseloinygkakxxdu.supabase.co/postgres"}, "sb_publishable_test")
        with self.assertRaises(RuntimeError):
            activation.settings_for({}, "sb_secret_test")

    def test_only_dedicated_bindings_and_sandbox_payments(self):
        dsn = "postgresql://postgres.atyhhjwwxgzeurnwayay:synthetic@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
        result = activation.settings_for({"STAGING_DATABASE_URL": dsn}, "sb_publishable_test")
        self.assertTrue(activation.validate_dedicated_staging_bindings(result))
        self.assertEqual(result["PAYFAST_MODE"], "sandbox")
        self.assertEqual(result["PAYFAST_ENV"], "sandbox")
        self.assertEqual(result["DATABASE_SCHEMA"], "public")
        self.assertEqual(result["SUPABASE_S3_ADMIN_BUCKET"], "amaris-staging-admin")
        self.assertEqual(result["SUPABASE_S3_STUDENT_BUCKET"], "amaris-staging-students")

    def test_wrong_service_rejected_before_any_environment_change(self):
        with patch.object(activation, "render", return_value={"ownerId": "other", "branch": "production"}), patch.object(activation, "prepare") as prepare:
            with self.assertRaises(RuntimeError):
                activation.main()
            prepare.assert_not_called()

    def test_signed_download_failure_still_deletes_synthetic_object(self):
        client = MagicMock()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"unexpected contents"
        with patch.object(activation.boto3, "client", return_value=client), patch.object(activation.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(RuntimeError):
                activation.storage_smoke({"AWS_ACCESS_KEY_ID": "synthetic", "AWS_SECRET_ACCESS_KEY": "synthetic"})
            client.delete_object.assert_called_once()


if __name__ == "__main__":
    unittest.main()
