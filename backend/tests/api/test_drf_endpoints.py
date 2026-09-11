from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.models import (
    FAQ,
    Announcement,
    ContactEnquiry,
    Course,
    CourseCategory,
    NavigationItem,
    Page,
    PricingPlan,
    SiteSettings,
    Testimonial,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-tests-default",
        },
        "public_content": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-tests-public",
        },
    }
)
class PublicDrfEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = CourseCategory.objects.create(name="CAPS", slug="caps")
        self.course = Course.objects.create(
            category=self.category,
            title="Grade 12 Mathematics",
            slug="grade-12-mathematics",
            short_description="Structured revision",
            description="Full Grade 12 mathematics revision course.",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            status=Course.Status.PUBLISHED,
            featured=True,
        )
        SiteSettings.objects.create()
        NavigationItem.objects.create(label="Home", url="/", location="header", order=1)
        Page.objects.create(
            title="About",
            slug="about",
            summary="About Amaris",
            is_published=True,
        )
        PricingPlan.objects.create(
            name="Monthly",
            slug="monthly",
            price=1800,
            is_published=True,
        )
        Testimonial.objects.create(
            student_name="Test Student",
            quote="A useful and structured learning experience.",
            rating=5,
            is_published=True,
        )
        FAQ.objects.create(
            question="How does it work?",
            answer="Register, verify your email, then enrol.",
            category="General",
            is_published=True,
        )
        Announcement.objects.create(
            title="Welcome",
            message="Registration is open.",
            is_published=True,
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )

    def test_settings_get_status_and_schema(self):
        response = self.client.get(reverse("site-settings"), secure=True)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("site_name", payload)
        self.assertNotIn("maintenance_mode", payload)

    def test_bootstrap_get_status_and_schema(self):
        response = self.client.get(reverse("site-bootstrap"), secure=True)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"settings", "navigation", "announcements"})
        self.assertIsInstance(payload["navigation"], list)
        self.assertIsInstance(payload["announcements"], list)

    def test_course_list_is_paginated_and_filters(self):
        response = self.client.get(reverse("courses-list"), {"curriculum": "CAPS"}, secure=True)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("count", payload)
        self.assertIn("results", payload)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["slug"], self.course.slug)

    def test_course_search_and_ordering(self):
        searched = self.client.get(reverse("courses-list"), {"search": "Mathematics"}, secure=True)
        self.assertEqual(searched.status_code, 200)
        self.assertEqual(searched.json()["count"], 1)

        ordered = self.client.get(reverse("courses-list"), {"ordering": "price"}, secure=True)
        self.assertEqual(ordered.status_code, 200)
        self.assertEqual(ordered.json()["results"][0]["slug"], self.course.slug)

    def test_course_invalid_identifier_returns_404(self):
        response = self.client.get(reverse("courses-detail", kwargs={"slug": "does-not-exist"}), secure=True)
        self.assertEqual(response.status_code, 404)

    def test_read_only_endpoints_reject_post_patch_delete(self):
        detail = reverse("courses-detail", kwargs={"slug": self.course.slug})
        self.assertEqual(self.client.post(reverse("courses-list"), {}, format="json", secure=True).status_code, 405)
        self.assertEqual(self.client.patch(detail, {"title": "Nope"}, format="json", secure=True).status_code, 405)
        self.assertEqual(self.client.delete(detail, secure=True).status_code, 405)

    def test_non_paginated_endpoints_return_lists(self):
        checks = [
            "navigation-list",
            "pages-list",
            "course-categories-list",
            "pricing-plans-list",
            "testimonials-list",
            "faqs-list",
            "announcements-list",
        ]
        for name in checks:
            with self.subTest(name=name):
                response = self.client.get(reverse(name), secure=True)
                self.assertEqual(response.status_code, 200)
                self.assertIsInstance(response.json(), list)

    def test_faq_filtering(self):
        response = self.client.get(reverse("faqs-list"), {"category": "General"}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {
            "anon": "1000/min",
            "user": "1000/min",
            "enquiries": "2/min",
        }
    },
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-tests-throttle",
        },
        "public_content": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-tests-public-enquiry",
        },
    },
)
class EnquiryApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("enquiries-list")
        self.valid_payload = {
            "name": "API Test",
            "email": "api-test@example.com",
            "phone": "0712345678",
            "subject": "Course enquiry",
            "message": "I would like more information about the mathematics course.",
        }

    def test_valid_post_creates_enquiry_and_response_schema(self):
        response = self.client.post(self.url, self.valid_payload, format="json", secure=True)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"name", "email", "phone", "subject", "message"})
        self.assertEqual(ContactEnquiry.objects.count(), 1)

    def test_duplicate_requests_are_independent_but_valid(self):
        first = self.client.post(self.url, self.valid_payload, format="json", secure=True)
        second = self.client.post(self.url, self.valid_payload, format="json", secure=True)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(ContactEnquiry.objects.count(), 2)

    def test_malformed_payload_returns_400(self):
        response = self.client.post(
            self.url,
            {"name": "A", "email": "not-an-email", "subject": "x", "message": "short"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("email", payload)
        self.assertIn("message", payload)

    def test_invalid_json_returns_400(self):
        response = self.client.generic(
            "POST",
            self.url,
            b'{"name":',
            content_type="application/json",
            secure=True,
        )
        self.assertEqual(response.status_code, 400)

    def test_unsupported_methods_are_rejected(self):
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 405)
        self.assertEqual(self.client.put(self.url, self.valid_payload, format="json", secure=True).status_code, 405)
        self.assertEqual(self.client.patch(self.url, self.valid_payload, format="json", secure=True).status_code, 405)
        self.assertEqual(self.client.delete(self.url, secure=True).status_code, 405)

    def test_rate_limit_returns_429(self):
        self.assertEqual(self.client.post(self.url, self.valid_payload, format="json", secure=True).status_code, 201)
        self.assertEqual(self.client.post(self.url, self.valid_payload, format="json", secure=True).status_code, 201)
        limited = self.client.post(self.url, self.valid_payload, format="json", secure=True)
        self.assertEqual(limited.status_code, 429)

    def test_oversized_message_is_rejected_by_field_limit_when_configured(self):
        field = ContactEnquiry._meta.get_field("message")
        max_length = getattr(field, "max_length", None)
        if max_length is None:
            self.skipTest("ContactEnquiry.message currently has no max_length; request-size limits belong at proxy/server level.")
        payload = {**self.valid_payload, "message": "x" * (max_length + 1)}
        response = self.client.post(self.url, payload, format="json", secure=True)
        self.assertEqual(response.status_code, 400)
