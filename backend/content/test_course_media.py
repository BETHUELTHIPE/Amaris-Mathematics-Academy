from datetime import UTC, datetime
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .admin_media import VideoAssetForm
from .models import VideoAsset
from .services.course_media import (
    FOLDER,
    VIDEO_PREFIX,
    CourseFileStorage,
    begin_video_upload,
    lesson_playback_url,
    verify_video_upload,
)


@override_settings(ACADEMY_MEDIA_BUCKET="staging-academy-media")
class CourseMediaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(username="media-admin", password="admin-test-password")
        cls.staff = get_user_model().objects.create_user(username="media-staff", is_staff=True)

    @override_settings(
        STORAGES={
            **settings.STORAGES,
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
    )
    def test_admin_page_and_start_endpoint_require_superuser_for_direct_media(self):
        endpoint = reverse("admin:content_videoasset_begin_upload")
        payload = {"provider": "s3", "asset": "", "filename": "algebra.mp4", "title": "Algebra", "size": 20}
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(endpoint, payload, content_type="application/json").status_code, 403)
        self.client.force_login(self.admin)
        page = self.client.get(reverse("admin:content_videoasset_add"))
        self.assertContains(page, "data-academy-upload")
        self.assertContains(page, "Open the academy Vimeo folder")
        with patch("content.services.course_media.s3_client") as factory:
            factory.return_value.generate_presigned_url.return_value = "https://example.invalid/upload"
            response = self.client.post(endpoint, payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        params = factory.return_value.generate_presigned_url.call_args.kwargs["Params"]
        self.assertEqual(params["IfNoneMatch"], "*")
        self.assertEqual(params["ContentLength"], 20)
        self.assertTrue(params["Key"].startswith("academy-media/videos/"))
        self.assertIn("ticket", response.json())

    @patch("content.services.course_media.s3_client")
    def test_s3_verifies_identity_and_file_before_saving(self, factory):
        client = factory.return_value
        client.generate_presigned_url.return_value = "https://example.invalid/upload"
        upload = begin_video_upload(
            user_id=self.admin.pk, asset_id="", provider="s3", filename="algebra.webm", size=20, title="Algebra"
        )
        with self.assertRaises(ValidationError):
            verify_video_upload(upload["ticket"], user_id=self.staff.pk, asset_id="", provider="s3")
        client.head_object.return_value = {
            "ContentLength": 19,
            "ContentType": "video/webm",
            "ServerSideEncryption": "AES256",
        }
        bad = VideoAssetForm(
            data={"title": "Algebra", "provider": "s3", "duration_seconds": 0, "upload_ticket": upload["ticket"]},
            user=self.admin,
        )
        self.assertFalse(bad.is_valid())
        client.head_object.return_value["ContentLength"] = 20
        good = VideoAssetForm(data=bad.data, user=self.admin)
        self.assertTrue(good.is_valid(), good.errors)
        video = good.save()
        self.assertTrue(video.aws_media_key.endswith(".webm"))
        self.assertFalse(video.source_file)

    @override_settings(ACADEMY_VIMEO_TOKEN="fake-vimeo-token", ACADEMY_VIMEO_EMBED_DOMAINS=("academy.example.com",))
    @patch("content.services.course_media._vimeo")
    def test_vimeo_upload_targets_folder_and_checks_private_embed(self, vimeo):
        vimeo.side_effect = [
            {"uri": FOLDER},
            {"uri": "/videos/1234", "upload": {"upload_link": "https://files.tus.vimeo.com/upload/n"}},
            {},
            {
                "uri": "/videos/1234",
                "upload": {"status": "complete"},
                "privacy": {"view": "disable", "embed": "whitelist", "download": False},
                "parent_folder": {"uri": FOLDER},
            },
        ]
        upload = begin_video_upload(
            user_id=self.admin.pk, asset_id="", provider="vimeo", filename="math.mov", size=20, title="Math"
        )
        self.assertEqual(vimeo.call_args_list[1].args[2]["folder_uri"], FOLDER)
        self.assertEqual(vimeo.call_args_list[2].args, ("/videos/1234/privacy/domains/academy.example.com", "PUT"))
        video_id = verify_video_upload(upload["ticket"], user_id=self.admin.pk, asset_id="", provider="vimeo")
        self.assertEqual(
            lesson_playback_url(VideoAsset(provider="vimeo", vimeo_video_id=video_id)),
            "https://player.vimeo.com/video/1234",
        )

    @override_settings(
        ACADEMY_VIDEO_CLOUDFRONT_DOMAIN="academytest.cloudfront.net",
        ACADEMY_VIDEO_CLOUDFRONT_KEY_ID="TESTKEY",
    )
    def test_playback_links_sign_the_specific_object_and_expiration(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        with override_settings(ACADEMY_VIDEO_CLOUDFRONT_PRIVATE_KEY=pem):
            url = lesson_playback_url(
                VideoAsset(provider="s3", aws_media_key=f"{VIDEO_PREFIX}algebra + lesson.mp4")
            )
        parsed = urlsplit(url)
        fields = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "academytest.cloudfront.net")
        self.assertEqual(parsed.path, "/academy-media/videos/algebra%20%2B%20lesson.mp4")
        self.assertEqual(fields["Key-Pair-Id"], ["TESTKEY"])
        self.assertTrue(fields["Signature"][0])
        remaining = int(fields["Expires"][0]) - datetime.now(UTC).timestamp()
        self.assertGreater(remaining, 590)
        self.assertLessEqual(remaining, 600)

    @patch("content.services.course_media.storages")
    @patch("content.services.course_media.default_storage")
    def test_legacy_course_files_stay_on_existing_storage(self, legacy, storages):
        legacy.url.return_value = "/legacy/worksheet.pdf"
        legacy.exists.return_value = False
        aws = storages.__getitem__.return_value
        aws.save.return_value = "academy-media/resources/worksheet.pdf"
        storage = CourseFileStorage()
        self.assertEqual(storage.url("resources/worksheet.pdf"), "/legacy/worksheet.pdf")
        self.assertEqual(
            storage.save("resources/worksheet.pdf", ContentFile(b"fixture")), "academy-media/resources/worksheet.pdf"
        )
        self.assertEqual(aws.save.call_args.args[0], "academy-media/resources/worksheet.pdf")
