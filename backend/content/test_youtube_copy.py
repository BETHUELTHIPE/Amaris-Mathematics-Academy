import io
import json
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import VideoAsset, YouTubeLessonCopy
from .services.youtube_copy import perform_youtube_copy

CHANNEL = "UC" + "A" * 22
VIDEO = "abcdefghijk"
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=fixture"
FINISHED = {
    "id": VIDEO,
    "snippet": {"channelId": CHANNEL},
    "status": {"privacyStatus": "private", "embeddable": False},
}


@override_settings(
    ACADEMY_MEDIA_BUCKET="private-course-fixture",
    ACADEMY_YOUTUBE_CHANNEL_ID=CHANNEL,
    ACADEMY_YOUTUBE_CLIENT_ID="test-client",
    ACADEMY_YOUTUBE_CLIENT_SECRET="test-secret",
    ACADEMY_YOUTUBE_REFRESH_TOKEN="test-refresh",
)
class PrivateYouTubeCopyTests(TestCase):
    def setUp(self):
        self.asset = VideoAsset.objects.create(
            title="Approved mathematics lesson",
            provider=VideoAsset.Provider.S3,
            is_published=True,
            aws_media_key="academy-media/videos/fixture.mp4",
        )
        self.copy = YouTubeLessonCopy.objects.create(
            video=self.asset,
            channel_id=CHANNEL,
            source_bucket="private-course-fixture",
            source_key=self.asset.aws_media_key,
        )

    @patch("content.services.youtube_copy.s3_client")
    @patch("content.services.youtube_copy.google_request")
    def test_interrupted_upload_resumes_one_private_copy_without_replacing_s3(self, google, make_s3):
        s3 = make_s3.return_value
        s3.head_object.return_value = {"ContentLength": 8, "ETag": '"fixture"'}
        s3.get_object.side_effect = [{"Body": io.BytesIO(b"abcdefgh")}, {"Body": io.BytesIO(b"efgh")}]
        credentials = [(200, {}, {"access_token": "fixture"}), (200, {}, {"items": [{"id": CHANNEL}]})]
        google.side_effect = [
            *credentials,
            (200, {"Location": SESSION}, {}),
            (308, {}, {}),
            URLError("synthetic"),
            *credentials,
            (308, {"Range": "bytes=0-3"}, {}),
            (201, {}, FINISHED),
        ]

        perform_youtube_copy(self.copy.pk)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, self.copy.Status.FAILED)
        self.assertEqual(self.copy.upload_session, SESSION)
        perform_youtube_copy(self.copy.pk)
        perform_youtube_copy(self.copy.pk)
        self.copy.refresh_from_db()
        self.asset.refresh_from_db()

        self.assertEqual(self.copy.status, self.copy.Status.COMPLETE)
        self.assertEqual(self.copy.youtube_video_id, VIDEO)
        self.assertEqual(self.copy.upload_session, "")
        self.assertEqual(self.asset.provider, VideoAsset.Provider.S3)
        self.assertEqual(self.asset.youtube_video_id, "")
        self.assertEqual(google.call_count, 9)
        request = google.call_args_list[2].kwargs
        self.assertEqual(json.loads(request["data"])["status"], {"privacyStatus": "private", "embeddable": False})
        self.assertEqual(s3.get_object.call_args.kwargs["Range"], "bytes=4-7")
        self.assertEqual(s3.get_object.call_args.kwargs["IfMatch"], '"fixture"')

    @patch("content.services.youtube_copy.s3_client")
    @patch("content.services.youtube_copy.google_request")
    def test_mismatched_channel_cannot_initiate_upload(self, google, make_s3):
        make_s3.return_value.head_object.return_value = {"ContentLength": 8, "ETag": '"fixture"'}
        google.side_effect = [(200, {}, {"access_token": "fixture"}), (200, {}, {"items": [{"id": "UCother"}]})]
        perform_youtube_copy(self.copy.pk)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, self.copy.Status.FAILED)
        self.assertEqual(self.copy.upload_session, "")
        self.assertEqual(google.call_count, 2)

    @patch("content.services.youtube_copy.s3_client")
    @patch("content.services.youtube_copy.google_request")
    def test_provider_response_must_confirm_private_visibility(self, google, make_s3):
        make_s3.return_value.head_object.return_value = {"ContentLength": 8, "ETag": '"fixture"'}
        google.side_effect = [
            (200, {}, {"access_token": "fixture"}),
            (200, {}, {"items": [{"id": CHANNEL}]}),
            (200, {"Location": SESSION}, {}),
            (201, {}, {**FINISHED, "status": {"privacyStatus": "unlisted"}}),
        ]
        perform_youtube_copy(self.copy.pk)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, self.copy.Status.FAILED)
        self.assertIn("private copy", self.copy.issue)
        self.assertEqual(self.copy.youtube_video_id, "")
        self.assertEqual(self.copy.upload_session, SESSION)

    @patch("content.admin.upload_private_youtube_copy.delay")
    @override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_admin_action_requires_superuser_and_approved_s3_asset(self, enqueue):
        user_model = get_user_model()
        manager = user_model.objects.create_user(username="staff", is_staff=True)
        manager.user_permissions.add(Permission.objects.get(codename="change_videoasset"))
        url = reverse("admin:content_videoasset_changelist")
        action = {"action": "copy_to_private_youtube", "_selected_action": str(self.asset.pk), "index": "0"}
        self.client.force_login(manager)
        self.assertNotContains(self.client.get(url, secure=True), "Copy one published S3 lesson")
        self.client.post(url, action, secure=True)
        enqueue.assert_not_called()

        self.client.force_login(user_model.objects.create_superuser(username="owner"))
        self.asset.is_published = False
        self.asset.save(update_fields=["is_published"])
        self.client.post(url, action, secure=True)
        enqueue.assert_not_called()
        self.asset.is_published = True
        self.asset.save(update_fields=["is_published"])
        self.client.post(url, action, secure=True)
        enqueue.assert_called_once_with(self.copy.pk)
