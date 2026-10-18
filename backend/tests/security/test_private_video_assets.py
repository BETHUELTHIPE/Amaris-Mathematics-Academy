"""Provider-specific private learning media contracts (no external calls)."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from content.models import Course, CourseCategory, CourseModule, Lesson, VideoAsset


class PrivateVideoAssetTests(TestCase):
    def test_vimeo_url_extracts_video_id(self):
        video = VideoAsset(
            title="Private Vimeo lesson",
            provider=VideoAsset.Provider.VIMEO,
            vimeo_url="https://vimeo.com/123456789/abcd1234",
        )
        video.full_clean()
        self.assertEqual(video.vimeo_video_id, "123456789")

    def test_vimeo_player_url_extracts_video_id(self):
        video = VideoAsset(
            title="Private Vimeo lesson",
            provider=VideoAsset.Provider.VIMEO,
            vimeo_url="https://player.vimeo.com/video/123456789?h=abcd1234",
        )
        video.full_clean()
        self.assertEqual(video.vimeo_video_id, "123456789")

    def test_vimeo_rejects_untrusted_host_and_nonnumeric_id(self):
        video = VideoAsset(
            title="Invalid Vimeo lesson",
            provider=VideoAsset.Provider.VIMEO,
            vimeo_url="https://example.com/123456789",
        )
        with self.assertRaises(ValidationError):
            video.full_clean()
        video.vimeo_url = ""
        video.vimeo_video_id = "not-an-id"
        with self.assertRaises(ValidationError):
            video.full_clean()

    def test_youtube_rejects_non_youtube_url(self):
        video = VideoAsset(
            title="Invalid YouTube lesson",
            provider=VideoAsset.Provider.YOUTUBE,
            youtube_url="https://example.com/watch?v=abcdefghijk",
        )
        with self.assertRaises(ValidationError):
            video.full_clean()

    def test_s3_requires_existing_or_aws_video_file(self):
        video = VideoAsset(title="Missing file", provider=VideoAsset.Provider.S3)
        with self.assertRaises(ValidationError):
            video.full_clean()

    @override_settings(DEBUG=True, PRIVATE_VIDEO_S3_BUCKET_NAME="")
    def test_new_s3_file_metadata_does_not_call_external_provider(self):
        video = VideoAsset(
            title="AWS upload metadata",
            provider=VideoAsset.Provider.S3,
            aws_file="private-videos/2026/10/example.mp4",
        )
        video.full_clean()
        self.assertTrue(video.aws_file.name.startswith("private-videos/"))

    @override_settings(DEBUG=False, PRIVATE_VIDEO_S3_BUCKET_NAME="")
    def test_production_cannot_upload_aws_file_without_bucket(self):
        video = VideoAsset(
            title="Unconfigured AWS video",
            provider=VideoAsset.Provider.S3,
            aws_file="private-videos/example.mp4",
        )
        with self.assertRaises(ValidationError):
            video.full_clean()

    def test_only_superuser_can_manage_private_videos_in_django_admin(self):
        video_admin = admin.site._registry[VideoAsset]
        superuser = get_user_model().objects.create_superuser(
            username="video-owner",
            email="video-owner@example.com",
            password="StrongPass123!",
        )
        staff = get_user_model().objects.create_user(
            username="video-staff",
            email="video-staff@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        for user, expected in ((superuser, True), (staff, False)):
            request = RequestFactory().get("/admin/content/videoasset/")
            request.user = user
            with self.subTest(superuser=expected):
                self.assertEqual(video_admin.has_module_permission(request), expected)
                self.assertEqual(video_admin.has_view_permission(request), expected)
                self.assertEqual(video_admin.has_add_permission(request), expected)
                self.assertEqual(video_admin.has_change_permission(request), expected)
                self.assertEqual(video_admin.has_delete_permission(request), expected)

    def test_public_course_api_does_not_disclose_private_vimeo_reference(self):
        category = CourseCategory.objects.create(name="CAPS", slug="caps")
        course = Course.objects.create(
            category=category,
            title="Mathematics",
            slug="mathematics-private-video",
            short_description="Course description",
            description="Course lessons",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            status=Course.Status.PUBLISHED,
        )
        module = CourseModule.objects.create(
            course=course,
            title="Algebra",
            order=1,
            is_published=True,
        )
        video = VideoAsset.objects.create(
            title="Private Vimeo lesson",
            provider=VideoAsset.Provider.VIMEO,
            vimeo_video_id="123456789",
            vimeo_url="https://vimeo.com/123456789",
            is_published=True,
        )
        Lesson.objects.create(
            module=module,
            title="Lesson 1",
            slug="lesson-1",
            order=1,
            is_published=True,
            video=video,
        )
        response = self.client.get(reverse("courses-detail", kwargs={"slug": course.slug}), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("123456789", response.content.decode("utf-8"))
        self.assertNotIn("vimeo_url", response.content.decode("utf-8"))

class PrivateVideoAdminHTTPTests(TestCase):
    """Exercise real Django Admin requests, not only permission hooks."""

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_superuser(
            "private-video-owner", "video-owner@example.test", "SyntheticPass123!"
        )
        self.staff = User.objects.create_user(
            "private-video-staff",
            "video-staff@example.test",
            "SyntheticPass123!",
            is_staff=True,
        )
        # Even explicit Django model permissions cannot grant private-video management.
        self.staff.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="content", content_type__model="videoasset"
            )
        )
        self.asset = VideoAsset.objects.create(
            title="Original private lesson",
            provider=VideoAsset.Provider.YOUTUBE,
            youtube_video_id="M7lc1UVf-VE",
        )

    @staticmethod
    def form_data(**changes):
        return {
            "title": "New private lesson",
            "provider": "youtube",
            "youtube_video_id": "M7lc1UVf-VE",
            "youtube_url": "",
            "vimeo_video_id": "",
            "vimeo_url": "",
            "duration_seconds": 60,
            "transcript": "",
            "_save": "Save",
            **changes,
        }

    def test_superuser_can_create_update_publish_and_delete_private_video(self):
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(reverse("admin:content_videoasset_add"), secure=True).status_code,
            200,
        )
        added = self.client.post(
            reverse("admin:content_videoasset_add"), self.form_data(), secure=True
        )
        self.assertEqual(added.status_code, 302)
        asset = VideoAsset.objects.get(title="New private lesson")
        updated = self.client.post(
            reverse("admin:content_videoasset_change", args=[asset.pk]),
            self.form_data(title="Updated private lesson"),
            secure=True,
        )
        self.assertEqual(updated.status_code, 302)
        asset.refresh_from_db()
        self.assertEqual(asset.title, "Updated private lesson")
        published = self.client.post(
            reverse("admin:content_videoasset_changelist"),
            {"action": "publish_selected", "_selected_action": [str(asset.pk)]},
            secure=True,
        )
        self.assertEqual(published.status_code, 302)
        asset.refresh_from_db()
        self.assertTrue(asset.is_published)
        deleted = self.client.post(
            reverse("admin:content_videoasset_delete", args=[asset.pk]),
            {"post": "yes"},
            secure=True,
        )
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(VideoAsset.objects.filter(pk=asset.pk).exists())

    def test_staff_with_model_permissions_cannot_view_or_mutate_videos(self):
        self.client.force_login(self.staff)
        urls = (
            reverse("admin:content_videoasset_changelist"),
            reverse("admin:content_videoasset_add"),
            reverse("admin:content_videoasset_change", args=[self.asset.pk]),
            reverse("admin:content_videoasset_delete", args=[self.asset.pk]),
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, secure=True).status_code, 403)
        requests = (
            (urls[1], self.form_data()),
            (urls[2], self.form_data(title="Unauthorized update")),
            (urls[3], {"post": "yes"}),
            (
                urls[0],
                {"action": "publish_selected", "_selected_action": [str(self.asset.pk)]},
            ),
        )
        for url, data in requests:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, data, secure=True).status_code, 403)
        self.asset.refresh_from_db()
        self.assertFalse(self.asset.is_published)
        self.assertEqual(self.asset.title, "Original private lesson")
        self.assertEqual(VideoAsset.objects.count(), 1)

    def test_bulk_publish_rejects_invalid_asset_without_partial_changes(self):
        invalid = VideoAsset.objects.create(
            title="Unusable Vimeo lesson",
            provider=VideoAsset.Provider.VIMEO,
            vimeo_video_id="not-numeric",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("admin:content_videoasset_changelist"),
            {
                "action": "publish_selected",
                "_selected_action": [str(self.asset.pk), str(invalid.pk)],
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.asset.refresh_from_db()
        invalid.refresh_from_db()
        self.assertFalse(self.asset.is_published)
        self.assertFalse(invalid.is_published)

    def test_admin_form_rejects_invalid_provider_reference(self):
        self.client.force_login(self.owner)
        result = self.client.post(
            reverse("admin:content_videoasset_add"),
            self.form_data(
                title="Bad Vimeo lesson",
                provider="vimeo",
                youtube_video_id="",
                vimeo_video_id="not-numeric",
            ),
            secure=True,
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(VideoAsset.objects.count(), 1)
