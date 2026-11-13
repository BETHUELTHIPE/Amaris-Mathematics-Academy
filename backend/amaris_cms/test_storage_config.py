from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase

from botocore.stub import ANY, Stubber
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import override_settings

from amaris_cms.storage import LocalPrivateStorage, SupabaseS3Storage, admin_private_storage, tutor_private_storage
from amaris_cms.storage_config import ADMIN_BUCKET, STUDENT_BUCKET, TUTOR_BUCKET, build_storage_config


class StorageRoutingTests(TestCase):
    def s3(self, alias: str) -> SupabaseS3Storage:
        storage = storages[alias]
        assert isinstance(storage, SupabaseS3Storage)
        return storage

    def config(self, **changes):
        values: dict[str, Any] = {
            "debug": False,
            "required": False,
            "base_dir": Path("/synthetic"),
            "media_root": Path("/synthetic/media"),
            "endpoint": "https://example.storage.supabase.co/storage/v1/s3",
            "access_key": "synthetic-access",
            "secret_key": "synthetic-secret",
            "admin_bucket": ADMIN_BUCKET,
            "student_bucket": STUDENT_BUCKET,
            "tutor_bucket": TUTOR_BUCKET,
            "region": "us-east-1",
            "legacy_cms_prefix": False,
        }
        values.update(changes)
        return build_storage_config(**values)

    def no_s3(self, **changes):
        return self.config(
            endpoint="", access_key="", secret_key="", admin_bucket="", student_bucket="", tutor_bucket="", **changes
        )

    def test_tutor_application_documents_forms_and_admin_uploads_use_designated_bucket(self):
        uploads = [
            ("tutor_qualifications", "tutor-applications/applicant/application/document.pdf"),
            ("tutor_private", "tutor-personnel/tutor/form/leave.pdf"),
            ("tutor_private", "tutor-personnel/tutor/form/resignation.pdf"),
            ("admin_private", "admin-performance/live/period/report.pdf"),
            ("tutor_private", "videos/tutor-uploads/tutor/video.mp4"),
            ("default", "videos/thumbnails/photo.png"),
            ("default", "resources/tutor/lesson.pdf"),
        ]
        with override_settings(STORAGES=self.config()):
            for alias, key in uploads:
                with self.subTest(alias=alias, key=key):
                    storage = self.s3(alias)
                    expected_bucket = TUTOR_BUCKET if alias.startswith("tutor_") else ADMIN_BUCKET
                    client = storage.connection.meta.client
                    with Stubber(client) as stub:
                        stub.add_client_error(
                            "head_object",
                            service_error_code="404",
                            http_status_code=404,
                            expected_params={"Bucket": expected_bucket, "Key": key},
                        )
                        stub.add_response(
                            "put_object",
                            {},
                            {
                                "Bucket": expected_bucket,
                                "Key": key,
                                "Body": ANY,
                                "ContentType": ANY,
                                "ChecksumAlgorithm": ANY,
                            },
                        )
                        self.assertEqual(storage.save(key, ContentFile(b"synthetic private content")), key)
                        stub.assert_no_pending_responses()
                    self.assertFalse(storage.default_acl)
                    self.assertTrue(storage.querystring_auth)

    def test_student_storage_aliases_stay_in_student_bucket(self):
        with override_settings(STORAGES=self.config()):
            for alias in ("student_private", "student_data", "student_documents"):
                self.assertEqual(self.s3(alias).bucket_name, STUDENT_BUCKET)
                self.assertNotEqual(self.s3(alias).bucket_name, self.s3("tutor_private").bucket_name)

    def test_swapped_shared_or_misspelled_buckets_are_rejected(self):
        for changes in (
            {"admin_bucket": STUDENT_BUCKET, "student_bucket": ADMIN_BUCKET},
            {"admin_bucket": STUDENT_BUCKET},
            {"student_bucket": ADMIN_BUCKET},
            {"admin_bucket": "amaris-csm-files"},
            {"tutor_bucket": ADMIN_BUCKET},
            {"tutor_bucket": STUDENT_BUCKET},
            {"tutor_bucket": ""},
        ):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.config(**changes)

    def test_partial_credentials_and_non_https_are_rejected(self):
        for changes in ({"secret_key": ""}, {"endpoint": "http://example.invalid"}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.config(**changes)
        with self.assertRaises(RuntimeError):
            self.no_s3(required=True)

    def test_production_without_s3_never_saves_to_local_filesystem(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.no_s3(base_dir=root, media_root=root / "media")
            with override_settings(STORAGES=config):
                for alias in ("default", "tutor_private", "tutor_qualifications", "student_private"):
                    with self.subTest(alias=alias), self.assertRaises(OSError):
                        storages[alias].save("sensitive.pdf", ContentFile(b"private"))
            self.assertEqual(list(root.iterdir()), [])

    def test_development_form_files_are_outside_public_media_and_have_no_public_url(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with override_settings(STORAGES=self.no_s3(debug=True, base_dir=root, media_root=root / "media")):
                for alias in ("tutor_private", "tutor_qualifications"):
                    storage = storages[alias]
                    self.assertIsInstance(storage, LocalPrivateStorage)
                    key = storage.save("form.pdf", ContentFile(b"private"))
                    self.assertFalse(Path(storage.path(key)).is_relative_to(root / "media"))
                    with storage.open(key) as saved:
                        self.assertEqual(saved.read(), b"private")
                    with self.assertRaises(ValueError):
                        storage.url(key)

    def test_private_pdf_models_explicitly_select_tutor_storage(self):
        from content.performance_models import PerformanceDigest
        from content.tutor_personnel_models import TutorPersonnelForm

        with override_settings(STORAGES=self.config()):
            for model, selector_expected, bucket in (
                (TutorPersonnelForm, tutor_private_storage, TUTOR_BUCKET),
                (PerformanceDigest, admin_private_storage, ADMIN_BUCKET),
            ):
                selector = model._meta.get_field("pdf").deconstruct()[3]["storage"]
                self.assertIs(selector, selector_expected)
                self.assertEqual(selector().bucket_name, bucket)

    def test_legacy_cms_prefix_is_preserved_for_existing_cloud_files(self):
        with override_settings(STORAGES=self.config(legacy_cms_prefix=True)):
            for alias in ("default", "admin_private"):
                self.assertEqual(self.s3(alias).location, "cms")
            self.assertEqual(self.s3("student_private").location, "")
            self.assertEqual(self.s3("tutor_private").location, "")
