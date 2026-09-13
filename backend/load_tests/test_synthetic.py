import json
import tempfile
import unittest
from pathlib import Path

from test_data.factories import Factory
from test_data.generate import generate

from load_tests.synthetic import (
    verify_data_configuration,
    verify_dataset,
    verify_email,
    verify_identity,
    verify_isolation,
)


class SyntheticLoadSafetyTests(unittest.TestCase):
    def test_server_must_confirm_mock_payments_and_notification_sinks(self):
        body = {
            "environment": "staging",
            "syntheticOnly": True,
            "paymentMode": "mock",
            "notifications": "sink",
        }
        verify_isolation(body)
        for change in (
            {"environment": "production"},
            {"syntheticOnly": False},
            {"paymentMode": "live"},
            {"notifications": "smtp"},
        ):
            with self.assertRaises(ValueError):
                verify_isolation(body | change)

    def test_modified_personal_data_cannot_be_blessed_by_editing_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data"
            factory = Factory(students=2, tutors=1, courses=1, lessons_per_course=1)
            generate(factory, output)
            self.assertEqual(verify_dataset(output / "manifest.json"), factory)
            rows = output / "students.ndjson"
            rows.write_text(rows.read_text().replace("@amaris.test", "@gmail.com"))
            with self.assertRaises(ValueError):
                verify_dataset(output / "manifest.json")

    def test_real_login_and_mismatched_session_are_rejected(self):
        factory = Factory()
        verify_email("student-1475-0000000@amaris.test", factory)
        for email in (
            "real@gmail.com",
            "student-1475-9999999@amaris.test",
            "student-42-0000000@amaris.test",
        ):
            with self.assertRaises(ValueError):
                verify_email(email, factory)
        body = {
            "email": "student-1475-0000000@amaris.test",
            "authenticated": True,
            "emailVerified": True,
        }
        verify_identity(body, body["email"])
        for change in (
            {"email": "real@gmail.com"},
            {"emailVerified": False},
            {"authenticated": False},
        ):
            with self.assertRaises(ValueError):
                verify_identity(body | change, body["email"])

    def test_public_checks_need_no_personal_data_and_unsafe_configuration_blocks(self):
        self.assertIsNone(verify_data_configuration({}))
        for env in (
            {"LOADTEST_AUTH_BEARER": "opaque-session"},
            {"LOADTEST_ALLOW_WRITES": "true", "LOADTEST_ENVIRONMENT": "production"},
        ):
            with self.assertRaises(ValueError):
                verify_data_configuration(env)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data"
            generate(Factory(students=1, tutors=1, courses=1, lessons_per_course=1), output)
            env = {
                "LOADTEST_DATA_MANIFEST": str(output / "manifest.json"),
                "LOADTEST_LOGIN_EMAIL": "student-1475-0000000@amaris.test",
                "LOADTEST_ALLOW_WRITES": "true",
                "LOADTEST_PAYMENT_MODE": "mock",
                "LOADTEST_REGISTRATION_EMAIL_DOMAIN": "amaris.test",
            }
            self.assertIsInstance(verify_data_configuration(env), Factory)
            for change in (
                {"LOADTEST_PAYMENT_MODE": "live"},
                {"LOADTEST_REGISTRATION_EMAIL_DOMAIN": "gmail.com"},
            ):
                with self.assertRaises(ValueError):
                    verify_data_configuration(env | change)
            manifest = output / "manifest.json"
            content = json.loads(manifest.read_text())
            content["synthetic_only"] = False
            manifest.write_text(json.dumps(content))
            with self.assertRaises(ValueError):
                verify_dataset(manifest)
