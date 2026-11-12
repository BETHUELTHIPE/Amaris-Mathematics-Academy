import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.storage import InMemoryStorage
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.models import Course, CourseCategory, CourseModule, Enrollment, Lesson, Payment, StudentRecord
from content.services.payments import PaymentSecurityError, _fulfill_verified_payment
from content.services.subscriptions import (
    CURRICULUM_ALIASES,
    accessible_enrollments,
    add_calendar_months,
    create_subscription_checkout,
    process_subscription_notification,
    refresh_subscription_courses,
    subscription_invoice,
)
from content.subscription_models import CurriculumSubscription


@override_settings(COURSE_SUBSCRIPTIONS_ENABLED=True, PUBLIC_SITE_URL="https://academy.example.test")
class SubscriptionTests(TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"PAYFAST_MODE": "sandbox", "PUBLIC_API_URL": "https://api.example.test"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.student = StudentRecord.objects.create(supabase_user_id=uuid.uuid4(), email="subscription@example.test")
        category = CourseCategory.objects.create(name="Synthetic", slug="synthetic")
        self.course = Course.objects.create(
            category=category,
            title="CAPS maths",
            slug="caps-maths",
            curriculum="CAPS",
            price="950",
            status="published",
            is_published=True,
        )
        module = CourseModule.objects.create(course=self.course, title="Module", is_published=True)
        self.lesson = Lesson.objects.create(module=module, title="Lesson", slug="lesson", is_published=True)
        self.api = APIClient()
        self.api.force_authenticate(
            user=SimpleNamespace(student=self.student, pk=self.student.pk, is_authenticated=True)
        )

    def checkout(self, curriculum="caps", months=4, key="test-test-test"):
        return create_subscription_checkout(
            student=self.student, curriculum=curriculum, months=months, idempotency_key=key
        )

    def payload(self, item, **changes):
        return {
            "merchant_id": "10000100",
            "amount_gross": str(item.amount),
            "pf_payment_id": "test-" + item.reference,
            "m_payment_id": item.reference,
            "payment_status": "COMPLETE",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": f"{item.curriculum}:{item.months}",
            **changes,
        }

    def paid(self):
        item, _, _ = self.checkout()
        result = process_subscription_notification(
            self.payload(item), gateway=Mock(verify_notification=Mock(return_value=True))
        )
        self.assertTrue(result.accepted)
        item.refresh_from_db()
        return item

    def test_all_curricula_same_prices_and_no_access_before_payment(self):
        for curriculum in CURRICULUM_ALIASES:
            for months, price in [(4, "3800.00"), (8, "7600.00")]:
                item, url, fields = self.checkout(curriculum, months, f"key-{curriculum}-{months}")
                self.assertEqual(fields["amount"], price)
                self.assertIn("sandbox.payfast.co.za", url)
                self.assertNotIn("subscription_type", fields)
                self.assertEqual(item.status, "pending")
                self.assertIsNone(item.ends_at)
        refresh_subscription_courses(self.student)
        self.assertFalse(Enrollment.objects.exists())

    def test_retries_are_idempotent_and_changed_selection_is_rejected(self):
        first, _, _ = self.checkout()
        self.assertEqual(first.pk, self.checkout()[0].pk)
        self.assertEqual(first.pk, self.checkout(key="another-unique-key")[0].pk)
        with self.assertRaises(PaymentSecurityError):
            self.checkout("ieb")
        self.assertEqual(CurriculumSubscription.objects.count(), 1)

    def test_callback_requires_independent_verification_amount_identity_and_mode(self):
        item, _, _ = self.checkout()
        for changes in (
            {"amount_gross": "1.00"},
            {"amount_gross": "NaN"},
            {"custom_str1": str(uuid.uuid4())},
            {"custom_str2": "ieb:8"},
            {"merchant_id": "wrong"},
        ):
            self.assertFalse(
                process_subscription_notification(
                    self.payload(item, **changes), gateway=Mock(verify_notification=Mock(return_value=True))
                ).accepted
            )
        self.assertFalse(
            process_subscription_notification(
                self.payload(item), gateway=Mock(verify_notification=Mock(return_value=False))
            ).accepted
        )
        with patch.dict(
            os.environ, {"PAYFAST_MODE": "live", "PAYFAST_MERCHANT_ID": "live", "PAYFAST_MERCHANT_KEY": "synthetic"}
        ):
            self.assertFalse(
                process_subscription_notification(
                    self.payload(item), gateway=Mock(verify_notification=Mock(return_value=True))
                ).accepted
            )
        item.refresh_from_db()
        self.assertIsNone(item.starts_at)

    def test_calendar_terms_and_duplicate_callbacks_do_not_extend_access(self):
        january = datetime(2026, 1, 31, tzinfo=UTC)
        self.assertEqual(add_calendar_months(january, 4).date().isoformat(), "2026-05-31")
        self.assertEqual(add_calendar_months(january, 8).date().isoformat(), "2026-09-30")
        item = self.paid()
        end = item.ends_at
        result = process_subscription_notification(
            self.payload(item), gateway=Mock(verify_notification=Mock(return_value=True))
        )
        self.assertTrue(result.duplicate)
        item.refresh_from_db()
        self.assertEqual(item.ends_at, end)

    def test_expiry_refund_and_curriculum_change_remove_subscription_lesson_access(self):
        item = self.paid()
        refresh_subscription_courses(self.student)
        path = reverse("student-lesson", args=[self.course.slug, self.lesson.slug])
        self.assertEqual(self.api.get(path, secure=True).status_code, 200)
        progress = self.api.patch(
            reverse("student-progress"),
            {
                "course_slug": self.course.slug,
                "lesson_slug": self.lesson.slug,
                "position_seconds": 42,
                "progress_percent": 12,
            },
            format="json",
            secure=True,
        )
        self.assertEqual(progress.status_code, 200)
        self.course.curriculum = "IEB"
        self.course.save()
        self.assertEqual(self.api.get(path, secure=True).status_code, 404)
        self.course.curriculum = "CAPS"
        self.course.save()
        item.ends_at = timezone.now() - timedelta(seconds=1)
        item.save()
        self.assertEqual(self.api.get(path, secure=True).status_code, 404)
        item.ends_at = timezone.now() + timedelta(days=1)
        item.status = "refunded"
        item.save()
        self.assertEqual(self.api.get(path, secure=True).status_code, 404)
        self.assertFalse(Enrollment.objects.filter(accessible_enrollments()).exists())

    def test_status_private_return_parameters_cannot_activate_and_price_is_server_owned(self):
        for invalid in ({"months": 4}, {"curriculum": "all", "months": 4}, {"curriculum": "caps", "months": 12}):
            response = self.api.post(
                reverse("subscription-checkout"),
                {**invalid, "idempotency_key": "invalid-selection"},
                format="json",
                secure=True,
            )
            self.assertEqual(response.status_code, 400)
        response = self.api.post(
            reverse("subscription-checkout"),
            {"curriculum": "university", "months": 8, "idempotency_key": "private-api-test", "amount": "0.01"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["fields"]["amount"], "7600.00")
        reference = response.data["subscription"]["reference"]
        path = reverse("subscription-status", args=[reference])
        status = self.api.get(path + "?status=paid", secure=True)
        self.assertFalse(status.data["active"])
        self.assertEqual(status["Cache-Control"], "private, no-store")
        other = StudentRecord.objects.create(supabase_user_id=uuid.uuid4(), email="other@example.test")
        self.api.force_authenticate(user=SimpleNamespace(student=other, pk=other.pk, is_authenticated=True))
        self.assertEqual(self.api.get(path, secure=True).status_code, 404)
        self.api.force_authenticate(user=None)
        self.assertEqual(self.api.get(path, secure=True).status_code, 401)

    def test_separate_verified_course_purchase_survives_subscription_expiry(self):
        item = self.paid()
        refresh_subscription_courses(self.student)
        payment = Payment.objects.create(
            reference="synthetic-direct-course-purchase",
            student=self.student,
            course=self.course,
            provider="payfast",
            status="paid",
            amount=self.course.price,
            gateway_verified_at=timezone.now(),
            paid_at=timezone.now(),
        )
        with self.captureOnCommitCallbacks(execute=False):
            _fulfill_verified_payment(payment)
        item.ends_at = timezone.now() - timedelta(seconds=1)
        item.save()
        path = reverse("student-lesson", args=[self.course.slug, self.lesson.slug])
        self.assertEqual(self.api.get(path, secure=True).status_code, 200)
        self.assertIsNone(Enrollment.objects.get(student=self.student, course=self.course).subscription_access_id)

    def test_paid_invoice_uses_existing_pdf_renderer_and_private_storage(self):
        item = self.paid()
        storage = InMemoryStorage()
        with patch("content.services.subscriptions.storages", {"student_private": storage}):
            with subscription_invoice(item) as document:
                data = document.read()
            self.assertTrue(data.startswith(b"%PDF"))
            item.refresh_from_db()
            self.assertTrue(item.pdf_storage_path.startswith(str(self.student.supabase_user_id)))
            with subscription_invoice(item) as document:
                self.assertEqual(document.read(), data)

    @override_settings(COURSE_SUBSCRIPTIONS_ENABLED=False)
    def test_payment_launch_gate_defaults_closed(self):
        with self.assertRaises(PaymentSecurityError):
            self.checkout()
