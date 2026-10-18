"""Provider-specific private learning media contracts (no external calls)."""

from django.contrib import admin
from django.contrib.auth import get_user_model
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
