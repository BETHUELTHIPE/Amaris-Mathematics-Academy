"""50,001-course catalogue regression with synthetic data only.

This checks the last catalogue page and checkout after the 50,000th
product. It does not perform external PayFast requests or live purchases.
"""

import uuid
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from content.models import Course, CourseCategory, Payment, StudentRecord
from content.services.payments import create_checkout


class CatalogOverFiftyThousandTests(TestCase):
    COURSE_COUNT = 50_001
    PAGE_SIZE = 24

    @classmethod
    def setUpTestData(cls):
        category = CourseCategory.objects.create(
            name="50k scale catalogue", slug="50k-scale-catalogue"
        )
        # Keep Python memory bounded and avoid one giant PostgreSQL insert.
        # PUBLISHED and is_published must be consistent because bulk_create
        # deliberately bypasses the Course.save() synchronization.
        for start in range(0, cls.COURSE_COUNT, 1_000):
            end = min(start + 1_000, cls.COURSE_COUNT)
            Course.objects.bulk_create(
                [
                    Course(
                        category=category,
                        title=f"Scalable Course {number:05d}",
                        slug=f"scalable-course-{number:05d}",
                        short_description="Synthetic mathematics course",
                        description="Non-public test fixture used for catalogue scaling.",
                        curriculum="CAPS",
                        academic_level="Grade 12",
                        price=Decimal("950.00"),
                        status=Course.Status.PUBLISHED,
                        is_published=True,
                        order=0,
                    )
                    for number in range(start, end)
                ],
                batch_size=500,
            )

    @patch.dict("os.environ", {"PAYFAST_MODE": "sandbox"})
    def test_course_50001_can_be_found_and_purchased_without_catalogue_truncation(self):
        last_page = (self.COURSE_COUNT - 1) // self.PAGE_SIZE + 1
        response = self.client.get(
            reverse("courses-list"), {"page": last_page, "page_size": self.PAGE_SIZE},
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["count"], self.COURSE_COUNT)
        self.assertEqual(len(result["results"]), 9)
        self.assertEqual(result["results"][-1]["slug"], "scalable-course-50000")
        self.assertIsNone(result["next"])

        # The search must span the database, not just the first 24 courses.
        found = self.client.get(
            reverse("courses-list"),
            {"search": "Scalable Course 50000"},
            secure=True,
        )
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["count"], 1)
        self.assertEqual(found.json()["results"][0]["slug"], "scalable-course-50000")
        self.assertEqual(found.json()["results"][0]["lesson_count"], 0)

        course = Course.objects.get(slug="scalable-course-50000")
        detail = self.client.get(
            reverse("courses-detail", kwargs={"slug": course.slug}),
            secure=True,
        )
        self.assertEqual(detail.status_code, 200)
        student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="course-50001@example.test",
            first_name="Scale",
            last_name="Student",
        )
        checkout = create_checkout(
            student=student, course=course,
            idempotency_key="catalog-fifty-thousand-one",
        )
        payment = Payment.objects.get(reference=checkout.payment_reference)
        self.assertEqual(payment.course_id, course.pk)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, course.price)
        self.assertEqual(checkout.fields["amount"], "950.00")
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)
