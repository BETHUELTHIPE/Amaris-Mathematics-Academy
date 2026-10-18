from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from content.models import Announcement
from content.youtube import normalise_youtube_url

VIDEO = "M7lc1UVf-VE"
PLAYLIST = "PLU1CWISq1SWo"


class YouTubeLinkTests(SimpleTestCase):
    def test_video_formats_are_normalised_and_tracking_removed(self):
        urls = [
            f"https://youtu.be/{VIDEO}?si=tracking",
            f"https://www.youtube.com/watch?v={VIDEO}&list={PLAYLIST}",
            f"https://m.youtube.com/shorts/{VIDEO}",
            f"https://www.youtube.com/live/{VIDEO}",
            f"https://www.youtube-nocookie.com/embed/{VIDEO}?autoplay=1",
            f"https://studio.youtube.com/video/{VIDEO}/edit",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(normalise_youtube_url(url), f"https://www.youtube.com/watch?v={VIDEO}")

    def test_studio_playlist_becomes_public_playlist_url(self):
        for url in (
            f"https://studio.youtube.com/playlist/{PLAYLIST}/videos",
            f"https://www.youtube.com/playlist?list={PLAYLIST}",
            f"https://www.youtube-nocookie.com/embed/videoseries?list={PLAYLIST}",
        ):
            with self.subTest(url=url):
                self.assertEqual(normalise_youtube_url(url), f"https://www.youtube.com/playlist?list={PLAYLIST}")

    def test_reject_unsafe_or_incomplete_links(self):
        for url in (
            "javascript:alert(1)",
            "//youtube.com/watch?v=" + VIDEO,
            "http://youtu.be/" + VIDEO,
            "https://youtube.com.attacker.test/watch?v=" + VIDEO,
            "https://youtube.com@attacker.test/watch?v=" + VIDEO,
            "https://user:password@youtube.com/watch?v=" + VIDEO,
            "https://www.youtube.com/watch?v=invalid",
            "https://studio.youtube.com/",
            "https://youtu.be/" + VIDEO + "\n?x=1",
            "https://www.youtube.com/playlist?list=<script>",
            "https://www.youtube.com\\@attacker.test/watch?v=" + VIDEO,
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                normalise_youtube_url(url)
        self.assertEqual(normalise_youtube_url(""), "")


class AnnouncementYouTubePermissionsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("youtube_super", "super@example.test", "synthetic-test-password")
        self.staff = User.objects.create_user("youtube_staff", is_staff=True)
        self.staff.user_permissions.set(
            Permission.objects.filter(content_type__app_label="content", content_type__model="announcement")
        )
        self.student = User.objects.create_user("youtube_student")
        self.notice = Announcement.objects.create(title="Academy video", message="Latest academy news")

    def form_data(self, **extra):
        return {
            "title": "Academy video",
            "message": "Latest academy news",
            "priority": 0,
            "youtube_url": f"https://studio.youtube.com/playlist/{PLAYLIST}/videos",
            "media-TOTAL_FORMS": 0,
            "media-INITIAL_FORMS": 0,
            "media-MIN_NUM_FORMS": 0,
            "media-MAX_NUM_FORMS": 1000,
            **extra,
        }

    def test_superuser_creates_publishes_updates_unpublishes_and_deletes(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:content_announcement_add"), self.form_data(is_published="on"), secure=True
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        notice = Announcement.objects.exclude(pk=self.notice.pk).get()
        self.assertEqual(notice.youtube_url, f"https://www.youtube.com/playlist?list={PLAYLIST}")
        self.assertTrue(notice.is_published)
        response = self.client.post(
            reverse("admin:content_announcement_change", args=[notice.pk]),
            self.form_data(youtube_url=f"https://youtu.be/{VIDEO}", is_published="on"),
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        notice.refresh_from_db()
        self.assertEqual(notice.youtube_url, f"https://www.youtube.com/watch?v={VIDEO}")
        response = self.client.post(
            reverse("admin:content_announcement_changelist"),
            {"action": "unpublish_selected", "_selected_action": [notice.pk]},
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        notice.refresh_from_db()
        self.assertFalse(notice.is_published)
        response = self.client.post(
            reverse("admin:content_announcement_changelist"),
            {"action": "publish_selected", "_selected_action": [notice.pk]},
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        notice.refresh_from_db()
        self.assertTrue(notice.is_published)
        response = self.client.post(
            reverse("admin:content_announcement_delete", args=[notice.pk]), {"post": "yes"}, secure=True
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Announcement.objects.filter(pk=notice.pk).exists())

    def test_staff_with_all_model_permissions_and_students_cannot_write(self):
        for user, expected in ((self.staff, 403), (self.student, 302)):
            self.client.force_login(user)
            for url, data in (
                (reverse("admin:content_announcement_add"), self.form_data(is_published="on")),
                (reverse("admin:content_announcement_change", args=[self.notice.pk]), self.form_data()),
                (reverse("admin:content_announcement_delete", args=[self.notice.pk]), {"post": "yes"}),
                (
                    reverse("admin:content_announcement_changelist"),
                    {"action": "publish_selected", "_selected_action": [self.notice.pk]},
                ),
            ):
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.post(url, data, secure=True).status_code, expected)
        self.notice.refresh_from_db()
        self.assertFalse(self.notice.is_published)
        self.assertEqual(self.notice.youtube_url, "")

    def test_invalid_youtube_link_is_a_form_error(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:content_announcement_add"),
            self.form_data(youtube_url="https://attacker.test/embed/video"),
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter an HTTPS YouTube video or playlist link")
        self.assertEqual(Announcement.objects.count(), 1)

    def test_public_api_only_returns_published_current_youtube_notices(self):
        self.notice.youtube_url = f"https://www.youtube.com/watch?v={VIDEO}"
        self.notice.save()
        response = self.client.get("/api/v1/announcements/", secure=True)
        self.assertNotIn(self.notice.pk, [item["id"] for item in response.json()])
        self.notice.is_published = True
        self.notice.save()
        response = self.client.get("/api/v1/announcements/", secure=True)
        self.assertEqual(response.json()[0]["youtube_url"], self.notice.youtube_url)
        self.notice.expires_at = timezone.now()
        self.notice.save()
        self.assertEqual(self.client.get("/api/v1/announcements/", secure=True).json(), [])
