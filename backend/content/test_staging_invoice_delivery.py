from __future__ import annotations

import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.storage import storages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
from content.models import Course, CourseCategory, LiveClassBooking, StudentRecord, TutorAvailabilitySlot
from content.payment_models import Invoice
from content.services.live_classes import create_live_class_checkout, process_live_class_notification
from content.services.payments import create_checkout, process_payfast_notification
from content.tasks import deliver_live_class_confirmation, deliver_transactional_email


class ApprovedSyntheticGateway:
    def verify_notification(self, payload):
        return True


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STAGING_RECEIPTS_ALLOW_LOCAL_TEST_STORAGE=True,
)
class StagingInvoiceAcceptanceTests(TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        stage = override_settings(STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                        "OPTIONS": {"location": str(Path(self.tempdir.name) / "admin")}},
            "student_data": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                             "OPTIONS": {"location": str(Path(self.tempdir.name) / "student")}},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        })
        stage.enable()
        self.addCleanup(stage.disable)
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="staging.student@example.test",
            first_name="Staging", last_name="Student",
        )
        self.other = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="other.staging.student@example.test",
            first_name="Other", last_name="Student",
        )
        category = CourseCategory.objects.create(name="Staging Receipt CI", slug="staging-receipt-ci")
        self.course = Course.objects.create(
            category=category, title="Test Mathematics", slug="staging-test-mathematics",
            short_description="Isolated only", description="Staging only", curriculum="Test",
            academic_level="Grade 12", price=Decimal("950.00"), status=Course.Status.PUBLISHED,
        )
        tutor = get_user_model().objects.create_user(username="staging-ci-tutor")
        now = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)
        self.slot = TutorAvailabilitySlot.objects.create(
            tutor=tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12", starts_at=now, ends_at=now + timedelta(hours=1),
            zoom_join_url="https://zoom.example.test/j/00000", is_active=True,
        )

    def as_student(self, student):
        client = APIClient()
        client.force_authenticate(user=SupabaseStudentPrincipal(
            student=student, supabase_user_id=str(student.supabase_user_id), email=student.email
        ))
        return client

    def course_paid(self):
        checkout = create_checkout(
            student=self.student, course=self.course,
            idempotency_key="staging-receipt-course-20261017",
        )
        result = process_payfast_notification({
            "m_payment_id": checkout.payment_reference,
            "pf_payment_id": "TEST-STAGING-RECEIPT-COURSE",
            "payment_status": "COMPLETE",
            "amount_gross": "950.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": self.course.slug,
        }, gateway=ApprovedSyntheticGateway())
        self.assertTrue(result.accepted)
        return checkout

    def live_paid(self):
        checkout = create_live_class_checkout(
            student=self.student, slot=self.slot, topic="Staging calculus",
            idempotency_key="staging-receipt-live-20261017",
        )
        result = process_live_class_notification({
            "m_payment_id": checkout.booking_reference,
            "pf_payment_id": "TEST-STAGING-RECEIPT-LIVE",
            "payment_status": "COMPLETE",
            "amount_gross": "250.00",
            "custom_str1": str(self.student.supabase_user_id),
            "custom_str2": checkout.booking_reference,
        }, gateway=ApprovedSyntheticGateway())
        self.assertTrue(result.accepted)
        return checkout

    def assert_receipt(self, route, number):
        owner = self.as_student(self.student)
        stranger = self.as_student(self.other)
        self.assertEqual(stranger.get(route, secure=True).status_code, 404)
        self.assertIn(stranger.get(route, secure=True).status_code, (404,))
        pdf_response = owner.get(route, secure=True)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Cache-Control"], "private, no-store")
        pdf = b"".join(pdf_response.streaming_content)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        storage = storages["student_data"]
        key = f"invoices/{self.student.supabase_user_id}/{number}.pdf"
        self.assertTrue(storage.exists(key))
        with storage.open(key, "rb") as f:
            self.assertEqual(f.read(), pdf)
        return pdf

    def test_course_receipt_emailed_and_downloaded_identically(self):
        checkout = self.course_paid()
        invoice = Invoice.objects.get(payment__reference=checkout.payment_reference)
        route = reverse("student-course-invoice", args=[checkout.payment_reference])
        pdf = self.assert_receipt(route, invoice.invoice_number)
        self.assertEqual(deliver_transactional_email.run(), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertEqual(mail.outbox[0].attachments[0][0], f"{invoice.invoice_number}.pdf")
        self.assertEqual(mail.outbox[0].attachments[0][1], pdf)
        self.assertEqual(deliver_transactional_email.run(), 0)
        self.assertEqual(len(mail.outbox), 1)
        orders = self.as_student(self.student).get(reverse("student-orders"), secure=True)
        self.assertEqual(orders.status_code, 200)
        self.assertTrue(any(x["invoice_ready"] for x in orders.data if x["reference"] == checkout.payment_reference))

    def test_live_class_pdf_emailed_and_downloaded_identically(self):
        checkout = self.live_paid()
        booking = LiveClassBooking.objects.get(reference=checkout.booking_reference)
        route = reverse("live-class-invoice-download", args=[booking.reference])
        pdf = self.assert_receipt(route, booking.invoice_number)
        self.assertEqual(deliver_live_class_confirmation.run(), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertEqual(mail.outbox[0].attachments[0][0], f"{booking.invoice_number}.pdf")
        self.assertEqual(mail.outbox[0].attachments[0][1], pdf)

    def test_unverified_invoice_never_downloadable(self):
        checkout = create_checkout(
            student=self.student, course=self.course, idempotency_key="staging-unpaid-20261017"
        )
        response = self.as_student(self.student).get(
            reverse("student-course-invoice", args=[checkout.payment_reference]), secure=True
        )
        self.assertEqual(response.status_code, 404)

    def test_private_storage_disabled_by_default_even_after_verified_payment(self):
        checkout = self.course_paid()
        with override_settings(STAGING_RECEIPTS_ALLOW_LOCAL_TEST_STORAGE=False, STAGING_RECEIPTS_ENABLED=False):
            response = self.as_student(self.student).get(
                reverse("student-course-invoice", args=[checkout.payment_reference]), secure=True
            )
            self.assertEqual(response.status_code, 503)
        self.assertFalse(mail.outbox)
