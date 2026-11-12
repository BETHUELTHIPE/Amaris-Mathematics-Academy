"""Cold API query budgets with synthetic data; no live provider calls."""

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.models import (
    Announcement,
    AnnouncementMedia,
    Course,
    CourseCategory,
    CourseModule,
    Lesson,
    LiveClassBooking,
    SiteSettings,
    StudentRecord,
    TutorAvailabilitySlot,
)

TEST_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "api-query-throttles"},
    "public_content": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
}


@override_settings(CACHES=TEST_CACHES)
class ApiQueryBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tutor = get_user_model().objects.create_user("query-tutor", email="tutor@example.invalid")
        category = CourseCategory.objects.create(name="Query fixtures", slug="query-fixtures")
        cls.course = Course.objects.create(
            category=category,
            title="Published calculus",
            slug="published-calculus",
            short_description="Calculus overview",
            description="Long course copy. " * 1000,
            curriculum="University",
            academic_level="First year",
            price="250.00",
            status=Course.Status.PUBLISHED,
        )
        module = CourseModule.objects.create(course=cls.course, title="Calculus", order=1, is_published=True)
        for i in range(5):
            Lesson.objects.create(
                module=module,
                title=f"Lesson {i}",
                slug=f"lesson-{i}",
                order=i,
                is_published=True,
                lesson_body="Private lesson body. " * 10000,
            )
        Lesson.objects.create(module=module, title="Draft", slug="draft", order=8, is_published=False)
        Lesson.objects.create(
            module=module,
            title="Scheduled",
            slug="scheduled",
            order=9,
            is_published=True,
            publish_at=timezone.now() + timedelta(days=10),
        )
        SiteSettings.objects.create()
        for i in range(12):
            announcement = Announcement.objects.create(title=f"News {i}", message="Academy news", is_published=True)
            AnnouncementMedia.objects.create(
                announcement=announcement, title="Guide", kind="pdf", file=f"marketing/guide-{i}.pdf"
            )
        Announcement.objects.create(title="Draft news", message="Hidden", is_published=False)
        Announcement.objects.create(
            title="Scheduled news", message="Hidden", is_published=True, publish_at=timezone.now() + timedelta(days=1)
        )
        Announcement.objects.create(
            title="Expired news", message="Hidden", is_published=True, expires_at=timezone.now() - timedelta(days=1)
        )
        cls.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="student@example.invalid", first_name="Query", last_name="Student"
        )
        cls.reservations = {}
        now = timezone.now()
        for i in range(120):
            start = now + timedelta(days=i + 1)
            slot = TutorAvailabilitySlot.objects.create(
                tutor=cls.tutor,
                programme="university",
                subject="mathematics",
                level="First year",
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                zoom_join_url="https://zoom.example.invalid/j/123",
            )
            statuses = LiveClassBooking.Status.values
            booking_status = statuses[i % len(statuses)]
            cls.reservations[slot.pk] = booking_status not in {"expired", "cancelled"}
            LiveClassBooking.objects.create(
                reference=f"API-QUERY-{i}",
                idempotency_key=f"api-query-{i}",
                student=cls.student,
                slot=slot,
                programme=slot.programme,
                subject=slot.subject,
                level=slot.level,
                topic="Calculus",
                status=booking_status,
            )

    def setUp(self):
        self.client = APIClient()

    def test_bootstrap_batches_announcement_media(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("site-bootstrap"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["announcements"]), 12)
        for announcement in response.data["announcements"]:
            self.assertEqual(len(announcement["media"]), 1)
            self.assertIn("/api/v1/marketing-media/", announcement["media"][0]["download_url"])

    def test_tutor_dashboard_query_count_is_constant_at_slot_limit(self):
        self.client.force_authenticate(self.tutor)
        with self.assertNumQueries(4):
            response = self.client.get(reverse("tutor-dashboard"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["slots"]), 120)
        for slot in response.data["slots"]:
            self.assertEqual(slot["reserved"], self.reservations[slot["id"]])
            self.assertEqual(slot["editable"], not self.reservations[slot["id"]])
        for booking in response.data["bookings"]:
            if booking["status"] not in {"confirmed", "completed"}:
                self.assertEqual(booking["student_email"], "")
                self.assertEqual(booking["zoom_join_url"], "")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("Authorization", response["Vary"])

    def test_course_pagination_count_does_not_group_the_whole_lesson_table(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("courses-list"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["lesson_count"], 5)
        self.assertEqual(len(queries), 2)
        count_sql = queries[0]["sql"].upper()
        self.assertNotIn("GROUP BY", count_sql)
        self.assertNotIn('JOIN "CONTENT_LESSON"', count_sql)

    def test_course_outline_avoids_loading_private_lesson_bodies(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("courses-detail", args=[self.course.slug]), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), 3)
        self.assertEqual(len(response.data["modules"][0]["lessons"]), 5)
        self.assertNotIn("Private lesson body", str(response.data))
        self.assertFalse(any('"lesson_body"' in query["sql"] for query in queries))

    def test_course_pages_filters_and_empty_lesson_counts_keep_their_contract(self):
        for i in range(26):
            Course.objects.create(
                category=self.course.category,
                title=f"Extra course {i:02d}",
                slug=f"extra-course-{i}",
                short_description="No lessons yet",
                description="New course",
                curriculum="University",
                academic_level="First year",
                price="250.00",
                featured=True,
                status=Course.Status.PUBLISHED,
            )
        first = self.client.get(reverse("courses-list"), secure=True)
        second = self.client.get(reverse("courses-list"), {"page": 2}, secure=True)
        self.assertEqual(first.data["count"], 27)
        self.assertEqual(len(first.data["results"]), 24)
        self.assertEqual(len(second.data["results"]), 3)
        rows = first.data["results"] + second.data["results"]
        self.assertEqual(len({row["slug"] for row in rows}), 27)
        self.assertTrue(all(row["lesson_count"] == 0 for row in rows if row["slug"].startswith("extra-")))
        filtered = self.client.get(reverse("courses-list"), {"search": "calculus"}, secure=True)
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(filtered.data["results"][0]["lesson_count"], 5)
        featured = self.client.get(reverse("courses-featured"), secure=True)
        self.assertIsInstance(featured.data, list)
        self.assertEqual(len(featured.data), 26)
        self.assertTrue(all(row["lesson_count"] == 0 for row in featured.data))

    def test_tutor_dashboard_handles_unreserved_slots_without_per_slot_queries(self):
        LiveClassBooking.objects.all().delete()
        self.client.force_authenticate(self.tutor)
        with self.assertNumQueries(4):
            response = self.client.get(reverse("tutor-dashboard"), secure=True)
        self.assertEqual(response.data["bookings"], [])
        self.assertTrue(all(not slot["reserved"] and slot["editable"] for slot in response.data["slots"]))

    def test_unauthenticated_tutor_responses_are_not_cacheable(self):
        response = self.client.get(reverse("tutor-dashboard"), secure=True)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("Authorization", response["Vary"])
