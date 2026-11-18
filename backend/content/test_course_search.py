"""Synthetic catalogue search regression, privacy and pagination checks."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import caches
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from content.models import Course, CourseCategory, CourseModule, Lesson


@override_settings(
    CACHES={
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "public_content": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "search-tests"},
    }
)
class CourseSearchTests(TestCase):
    def setUp(self):
        for alias in ("default", "public_content"):
            caches[alias].clear()
        self.category = CourseCategory.objects.create(name="General courses", slug="general")
        self.counter = 0

    def course(self, title="Calculus", **changes):
        self.counter += 1
        return Course.objects.create(
            **{
                "category": self.category,
                "slug": f"synthetic-course-{self.counter}",
                "title": title,
                "short_description": "Structured revision and practice",
                "description": "Paid lesson content is not a search index.",
                "curriculum": "CAPS",
                "academic_level": "Grade 12",
                "price": Decimal("250.00"),
                "status": Course.Status.PUBLISHED,
                **changes,
            }
        )

    def search(self, **params):
        return self.client.get(reverse("courses-list"), params, secure=True)

    def slugs(self, response):
        self.assertEqual(response.status_code, 200)
        return [row["slug"] for row in response.json()["results"]]

    def test_search_finds_course_beyond_the_first_page(self):
        for index in range(30):
            self.course(f"Ordinary topic {index:03}", order=index)
        target = self.course("Advanced quaternion algebra", order=999)
        self.assertNotIn(target.slug, self.slugs(self.search()))
        self.assertEqual(self.slugs(self.search(search="quaternion")), [target.slug])

    def test_all_words_match_in_any_order_with_case_and_whitespace_normalization(self):
        target = self.course("Differential Calculus")
        self.course("Calculus for university", curriculum="Higher Education", academic_level="University")
        for query in ("CAPS calculus", "calculus CAPS", "   CAPS   CALCULUS   "):
            with self.subTest(query=query):
                self.assertEqual(self.slugs(self.search(search=query)), [target.slug])

    def test_common_maths_and_matric_aliases(self):
        target = self.course("Mathematics revision")
        self.course("Mathematics revision", academic_level="Grade 11")
        self.assertEqual(self.slugs(self.search(search="maths matric")), [target.slug])

    def test_grade_variants_and_grade_one_does_not_match_grade_twelve(self):
        twelve = self.course("Mathematics revision")
        one = self.course("Mathematics revision", academic_level="Grade 1")
        for query in ("Grade 12", "gr.12", "grade12"):
            self.assertEqual(self.slugs(self.search(search=query)), [twelve.slug])
        self.assertEqual(self.slugs(self.search(search="grade 1")), [one.slug])

    def test_ieb_filter_and_level_combine_with_search(self):
        target = self.course("Trigonometry", curriculum="IEB")
        self.course("Trigonometry", curriculum="IEB", academic_level="Grade 11")
        self.course("Trigonometry", curriculum="CAPS")
        self.assertEqual(
            self.slugs(self.search(search="trigonometry", programme="IEB", academic_level="Grade 12")),
            [target.slug],
        )

    def test_tvet_nated_ncv_and_unisa_programme_matching(self):
        nated = self.course("Engineering mathematics", curriculum="NATED", academic_level="TVET N4")
        ncv = self.course("Applied mathematics", curriculum="NC(V)", academic_level="Level 4")
        unisa = self.course("Linear algebra", curriculum="UNISA", academic_level="MAT1503")
        self.assertEqual(set(self.slugs(self.search(programme="TVET"))), {nated.slug, ncv.slug})
        self.assertEqual(self.slugs(self.search(programme="University")), [unisa.slug])
        self.assertEqual(self.slugs(self.search(search="ncv")), [ncv.slug])

    def test_exact_title_precedes_prefix_and_description_match(self):
        exact = self.course("Calculus", order=999)
        prefix = self.course("Calculus foundations", order=0)
        other = self.course("Advanced revision", short_description="Calculus explained", order=0)
        self.assertEqual(self.slugs(self.search(search="Calculus")), [exact.slug, prefix.slug, other.slug])

    def test_explicit_price_sort_overrides_relevance(self):
        expensive = self.course("Calculus", price=900)
        cheap = self.course("Calculus foundations", price=100)
        self.assertEqual(self.slugs(self.search(search="calculus", ordering="price")), [cheap.slug, expensive.slug])
        self.assertEqual(self.slugs(self.search(search="calculus", ordering="-price")), [expensive.slug, cheap.slug])

    def test_drafts_archived_future_and_inactive_categories_stay_private(self):
        public = self.course("Unique public calculus")
        self.course("Private calculus", status=Course.Status.DRAFT)
        self.course("Archived calculus", status=Course.Status.ARCHIVED)
        self.course("Scheduled calculus", publish_at=timezone.now() + timedelta(days=1))
        hidden = CourseCategory.objects.create(name="Hidden", slug="hidden", is_active=False)
        self.course("Hidden category calculus", category=hidden)
        response = self.search(search="calculus")
        self.assertEqual(self.slugs(response), [public.slug])
        self.assertEqual(response.json()["count"], 1)

    def test_paid_descriptions_and_lesson_text_are_not_searchable_or_serialized(self):
        course = self.course("Public metadata", description="PRIVATE-DESCRIPTION-SENTINEL")
        module = CourseModule.objects.create(course=course, title="Private module", is_published=False)
        Lesson.objects.create(
            module=module,
            title="PRIVATE-LESSON-SENTINEL",
            slug="private-lesson",
            is_published=True,
        )
        for token in ("PRIVATE-DESCRIPTION-SENTINEL", "PRIVATE-LESSON-SENTINEL"):
            self.assertEqual(self.slugs(self.search(search=token)), [])
        data = self.search().json()["results"][0]
        self.assertEqual(data["lesson_count"], 0)
        self.assertNotIn("description", data)
        self.assertNotIn("modules", data)

    def test_page_size_is_bounded_and_pages_are_stable_without_duplicates(self):
        for _ in range(60):
            self.course("Equal title")
        first = self.search(search="equal", page_size=10000)
        self.assertEqual(len(self.slugs(first)), 48)
        second = self.search(search="equal", page_size=10000, page=2)
        self.assertEqual(len(self.slugs(second)), 12)
        self.assertFalse(set(self.slugs(first)) & set(self.slugs(second)))
        self.assertEqual(first.json()["count"], 60)

    def test_invalid_and_excessive_search_is_a_safe_400(self):
        for query in ("x" * 101, "one two three four five six seven eight nine", "!!!"):
            response = self.search(search=query)
            self.assertEqual(response.status_code, 400)
            self.assertIn("search", response.json())

    def test_sql_like_input_never_expands_results(self):
        self.course("Geometry")
        self.assertEqual(self.slugs(self.search(search="' OR 1=1 --")), [])
        self.assertEqual(Course.objects.count(), 1)

    def test_category_metadata_is_searchable(self):
        category = CourseCategory.objects.create(name="Engineering", slug="engineering")
        target = self.course("Mathematics N4", category=category)
        self.assertEqual(self.slugs(self.search(search="Engineering")), [target.slug])

    def test_featured_endpoint_remains_bounded(self):
        for index in range(10):
            self.course(f"Featured {index}", featured=True)
        response = self.client.get(reverse("courses-featured"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 6)

    def test_search_response_query_count_is_bounded(self):
        for index in range(30):
            self.course(f"Calculus {index}")
        with CaptureQueriesContext(connection) as queries:
            response = self.search(search="calculus")
            self.assertEqual(len(response.json()["results"]), 24)
        self.assertLessEqual(len(queries), 3)
