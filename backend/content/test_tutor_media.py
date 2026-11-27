from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import VideoAsset
from .services.course_media import begin_video_upload


@override_settings(ACADEMY_MEDIA_BUCKET="staging-course-fixture")
class TutorMediaTests(TestCase):
    def setUp(self):
        cache.clear()
        group, _ = Group.objects.get_or_create(name="Tutors")
        self.tutor = get_user_model().objects.create_user(username="tutor", email="tutor@example.test")
        self.other = get_user_model().objects.create_user(username="other", email="other@example.test")
        self.student = get_user_model().objects.create_user(username="student", email="student@example.test")
        self.tutor.groups.add(group)
        self.other.groups.add(group)
        self.validate = self.enterContext(patch("content.tutor_views.SupabaseStudentAuthentication._validate_token"))
        self.storage = self.enterContext(patch("content.services.course_media.s3_client")).return_value
        self.storage.generate_presigned_url.return_value = "https://bucket.example.test/upload"
        self.storage.head_object.return_value = {
            "ContentLength": 64,
            "ContentType": "video/mp4",
            "ServerSideEncryption": "AES256",
        }
        self.details = {"provider": "s3", "filename": "algebra.mp4", "title": "Algebra", "size": 64}

    def signed_in(self, user, *, confirmed=True):
        self.validate.return_value = {
            "id": "supabase-test-user",
            "email": user.email,
            "email_confirmed_at": "2026-10-10" if confirmed else None,
        }
        return {"HTTP_AUTHORIZATION": "Bearer synthetic-fixture", "secure": True}

    def start(self, **headers):
        return self.client.post(reverse("tutor-video-start"), self.details, content_type="application/json", **headers)

    def finish(self, data, **headers):
        return self.client.post(reverse("tutor-video-finish"), data, content_type="application/json", **headers)

    def test_only_verified_approved_tutors_can_start_upload(self):
        self.assertEqual(self.start(secure=True).status_code, 401)
        self.assertEqual(self.start(**self.signed_in(self.student)).status_code, 401)
        self.assertEqual(self.start(**self.signed_in(self.tutor, confirmed=False)).status_code, 401)
        self.storage.generate_presigned_url.assert_not_called()
        settings = self.signed_in(self.tutor)
        self.details["provider"] = "vimeo"
        self.assertEqual(self.start(**settings).status_code, 400)
        self.details["provider"] = "s3"
        result = self.start(**settings)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result["Cache-Control"], "private, no-store")
        self.assertIn("submission", result.json())

    def test_cross_account_ticket_is_rejected_and_submission_is_private_and_idempotent(self):
        issued = self.start(**self.signed_in(self.tutor)).json()
        payload = {
            "provider": "s3",
            "ticket": issued["ticket"],
            "submission": issued["submission"],
            "title": "Spoofed title",
            "is_published": True,
            "submitted_by": self.other.pk,
        }
        self.assertEqual(self.finish(payload, **self.signed_in(self.other)).status_code, 400)
        self.storage.head_object.assert_not_called()
        assert not VideoAsset.objects.exists()
        result = self.finish(payload, **self.signed_in(self.tutor))
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.finish(payload, **self.signed_in(self.tutor)).status_code, 200)
        video = VideoAsset.objects.get()
        self.assertEqual(video.submitted_by, self.tutor)
        self.assertEqual(video.title, "Algebra")
        self.assertFalse(video.is_published)
        for user, expected in ((self.tutor, 1), (self.other, 0)):
            response = self.client.get(reverse("tutor-video-list"), **self.signed_in(user))
            self.assertEqual(len(response.json()["videos"]), expected)
            if expected:
                item = response.json()["videos"][0]
                self.assertFalse(item["ready"])
                self.assertNotIn("aws_media_key", item)
                self.assertNotIn("ticket", item)

    def test_admin_ticket_cannot_submit_as_tutor(self):
        asset_id = "d352c160-f885-4267-b5e5-3849f8693b0d"
        issued = begin_video_upload(user_id=self.tutor.pk, asset_id=asset_id, **self.details)
        result = self.finish(
            {"provider": "s3", "ticket": issued["ticket"], "submission": asset_id},
            **self.signed_in(self.tutor),
        )
        self.assertEqual(result.status_code, 400)
        self.storage.head_object.assert_not_called()

    @override_settings(
        ACADEMY_VIMEO_TOKEN="synthetic-token",
        ACADEMY_VIMEO_EMBED_DOMAINS=("academy.example.test",),
    )
    @patch("content.services.course_media._vimeo")
    def test_vimeo_is_verified_in_the_configured_folder_before_draft_is_saved(self, vimeo):
        from .services.course_media import FOLDER

        vimeo.side_effect = [
            {"uri": FOLDER},
            {"uri": "/videos/1543", "upload": {"upload_link": "https://files.tus.vimeo.com/upload/test"}},
            {},
            {
                "uri": "/videos/1543",
                "upload": {"status": "complete"},
                "privacy": {"view": "disable", "embed": "whitelist", "download": False},
                "parent_folder": {"uri": FOLDER},
            },
        ]
        self.details.update(provider="vimeo", filename="lesson.mov")
        credentials = self.signed_in(self.tutor)
        issue = self.start(**credentials)
        self.assertEqual(issue.status_code, 201)
        issued = issue.json()
        outcome = self.finish(
            {"provider": "vimeo", "ticket": issued["ticket"], "submission": issued["submission"]}, **credentials
        )
        self.assertEqual(outcome.status_code, 201)
        video = VideoAsset.objects.get()
        self.assertEqual(video.vimeo_video_id, "1543")
        self.assertFalse(video.is_published)
        self.assertEqual(vimeo.call_args_list[1].args[2]["folder_uri"], FOLDER)
