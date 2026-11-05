"""End-to-end catalogue and checkout regression at 601 published courses.

Synthetic data only: no real transactions, PayFast calls, or production writes.
"""
import uuid
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from content.models import Course, CourseCategory, Payment, StudentRecord
from content.services.payments import create_checkout


class LargeCourseCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="Scalable catalog", slug="scalable-catalog")
        batch = []
        for number in range(601):
            curriculum = "CAPS"
            level = "Grade 12"
            if number == 599:
                curriculum = "Higher Education"
                level = "University"
            elif number == 600:
                curriculum = "NATED"
                level = "TVET N4"
            batch.append(
                Course(
                    category=cls.category,
                    title=f"Course {number:04d}",
                    slug=f"course-{number:04d}",
                    short_description=f"Practice course {number:04d}",
                    description="Synthetic catalogue fixture for pagination and searching.",
                    curriculum=curriculum,
                    academic_level=level,
                    price=Decimal("1250.00") if number == 600 else Decimal("950.00"),
                    status=Course.Status.PUBLISHED,
                    is_published=True,  # bulk_create bypasses Course.save()
                    order=0,
                )
            )
        Course.objects.bulk_create(batch, batch_size=100)

    def test_601_courses_are_discoverable_without_loading_entire_catalogue(self):
        first = self.client.get(reverse("courses-list"), secure=True)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["count"], 601)
        self.assertEqual(len(first.json()["results"]), 24)
        self.assertIsNotNone(first.json()["next"])
        self.assertEqual(first.json()["results"][0]["slug"], "course-0000")

        last = self.client.get(reverse("courses-list"), {"page": 26}, secure=True)
        self.assertEqual(last.status_code, 200)
        self.assertEqual(last.json()["count"], 601)
        self.assertEqual([x["slug"] for x in last.json()["results"]], ["course-0600"])
        self.assertIsNone(last.json()["next"])

    def test_page_size_is_bounded_against_unlimited_api_download(self):
        oversized = self.client.get(
            reverse("courses-list"), {"page_size": 100000}, secure=True
        )
        self.assertEqual(oversized.status_code, 200)
        self.assertEqual(oversized.json()["count"], 601)
        self.assertEqual(len(oversized.json()["results"]), 48)

    def test_search_finds_course_that_was_on_last_page(self):
        response = self.client.get(
            reverse("courses-list"), {"search": "Course 0600"}, secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["slug"], "course-0600")

    def test_programme_filter_applies_before_pagination(self):
        caps = self.client.get(
            reverse("courses-list"), {"programme": "CAPS"}, secure=True
        )
        tvet = self.client.get(
            reverse("courses-list"), {"programme": "TVET"}, secure=True
        )
        university = self.client.get(
            reverse("courses-list"), {"programme": "University"}, secure=True
        )
        self.assertEqual(caps.json()["count"], 599)
        self.assertEqual(tvet.json()["count"], 1)
        self.assertEqual(tvet.json()["results"][0]["slug"], "course-0600")
        self.assertEqual(university.json()["count"], 1)
        self.assertEqual(university.json()["results"][0]["slug"], "course-0599")

    def test_checkout_is_available_for_course_beyond_first_500(self):
        student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="catalog-601@example.test",
            first_name="Catalogue",
            last_name="Student",
        )
        course = Course.objects.get(slug="course-0600")
        detail = self.client.get(
            reverse("courses-detail", kwargs={"slug": course.slug}), secure=True
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["slug"], "course-0600")

        checkout = create_checkout(
            student=student,
            course=course,
            idempotency_key="catalog-over-500-test-001",
        )
        payment = Payment.objects.get(reference=checkout.payment_reference)
        self.assertEqual(payment.course_id, course.pk)
        self.assertEqual(payment.amount, Decimal("1250.00"))
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(checkout.fields["amount"], "1250.00")
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)
        self.assertEqual(checkout.fields["custom_str2"], course.slug)

    def test_unpublished_items_remain_hidden_in_large_catalogue(self):
        Course.objects.create(
            category=self.category,
            title="Course unpublished",
            slug="course-unpublished",
            short_description="Not for sale",
            description="Not ready",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=Decimal("950.00"),
            status=Course.Status.DRAFT,
        )
        response = self.client.get(
            reverse("courses-list"), {"search": "unpublished"}, secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_featured_endpoint_is_bounded_for_homepage(self):
        Course.objects.filter(slug__in=[f"course-{number:04d}" for number in range(20)]).update(
            featured=True
        )
        response = self.client.get(reverse("courses-featured"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 6)
        self.assertTrue(all(item["featured"] for item in response.json()))
