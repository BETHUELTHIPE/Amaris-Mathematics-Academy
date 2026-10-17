"""Query-budget and payload regression tests for the public DRF course endpoints."""

from datetime import timedelta

from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Course, CourseCategory, CourseModule, Lesson


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "drf-catalog-query-default",
        },
        "public_content": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "drf-catalog-query-public",
        },
    }
)
class PublicCourseQueryEfficiencyTests(TestCase):
    def setUp(self):
        caches["public_content"].clear()
        category = CourseCategory.objects.create(name="Mathematics", slug="mathematics")
        self.courses = []
        for index in range(12):
            course = Course.objects.create(
                category=category,
                title=f"Mathematics {index:02d}",
                slug=f"mathematics-{index:02d}",
                short_description="Published mathematics",
                description="Long detail-page description",
                curriculum="CAPS",
                academic_level="Grade 12",
                price=950,
                featured=(index == 0),
                status=Course.Status.PUBLISHED,
            )
            module = CourseModule.objects.create(
                course=course, title="Algebra", order=1, is_published=True
            )
            for lesson_index in (1, 2):
                Lesson.objects.create(
                    module=module,
                    title=f"Lesson {lesson_index}",
                    slug=f"lesson-{lesson_index}",
                    order=lesson_index,
                    is_published=True,
                )
            self.courses.append((course, module))

    def test_paginated_list_uses_two_queries_for_twelve_courses(self):
        with self.assertNumQueries(2):
            response = self.client.get(reverse("courses-list"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 12)
        self.assertEqual(len(response.json()["results"]), 12)
        self.assertTrue(all(course["lesson_count"] == 2 for course in response.json()["results"]))
        self.assertNotIn("modules", response.json()["results"][0])
        self.assertNotIn("description", response.json()["results"][0])

        with self.assertNumQueries(0):
            cached_response = self.client.get(reverse("courses-list"), secure=True)
        self.assertEqual(cached_response.content, response.content)

    def test_featured_endpoint_does_not_make_one_query_per_course(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("courses-featured"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["lesson_count"], 2)

    def test_detail_prefetches_modules_and_lessons_without_n_plus_one(self):
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("courses-detail", kwargs={"slug": self.courses[0][0].slug}),
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lesson_count"], 2)
        self.assertEqual(len(response.json()["modules"]), 1)
        self.assertEqual(len(response.json()["modules"][0]["lessons"]), 2)

    def test_count_excludes_unpublished_and_future_lessons(self):
        course, module = self.courses[0]
        Lesson.objects.create(
            module=module,
            title="Draft",
            slug="draft-lesson",
            order=3,
            is_published=False,
        )
        Lesson.objects.create(
            module=module,
            title="Scheduled",
            slug="scheduled-lesson",
            order=4,
            is_published=True,
            publish_at=timezone.now() + timedelta(days=2),
        )
        response = self.client.get(
            reverse("courses-detail", kwargs={"slug": course.slug}), secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lesson_count"], 2)
        self.assertEqual(len(response.json()["modules"][0]["lessons"]), 2)

    def test_course_without_lessons_reports_zero_not_null(self):
        course, module = self.courses[0]
        Lesson.objects.filter(module=module).delete()
        response = self.client.get(
            reverse("courses-detail", kwargs={"slug": course.slug}), secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lesson_count"], 0)
        self.assertEqual(response.json()["modules"][0]["lessons"], [])
