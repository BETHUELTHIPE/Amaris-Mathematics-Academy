"""Production-branch tutor revenue regression tests: verified sales, privacy and payout safeguards."""

import uuid
from datetime import timedelta
from decimal import Decimal

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from content.models import (
    Course,
    CourseCategory,
    LiveClassBooking,
    Payment,
    StudentRecord,
    TutorAvailabilitySlot,
    VideoRequest,
)
from content.services.payments import create_checkout, process_payfast_notification
from content.services.tutor_finance import (
    record_course_sale,
    record_existing_video_sale,
    refresh_eligible_earnings,
    tutor_dashboard_stats,
)
from content.tutor_finance_admin import TutorPaymentProfileForm
from content.tutor_finance_models import (
    TutorContract,
    TutorCourseAssignment,
    TutorEarning,
    TutorPayout,
)
from content.tutor_finance_tasks import (
    email_tutor_payout_receipt,
    reconcile_tutor_earnings,
)


class VerifiedGateway:
    def __init__(self, accepted=True):
        self.accepted = accepted

    def verify_notification(self, payload):
        return self.accepted


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ProductionTutorFinanceTests(TestCase):
    def setUp(self):
        self.tutor = get_user_model().objects.create_user(
            username="finance.test.tutor",
            password="test-password-not-for-production",
            email="finance.tutor@example.test",
            first_name="Finance",
        )
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="confidential.student@example.test",
            first_name="PrivateStudent",
            last_name="Confidential",
        )
        category = CourseCategory.objects.create(
            name="Finance regression", slug="finance-regression"
        )
        self.course = Course.objects.create(
            category=category,
            title="Calculus tutorial",
            slug="finance-regression-calculus",
            short_description="Regression",
            description="Regression",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=Decimal("250.00"),
            status=Course.Status.PUBLISHED,
        )
        self.contract = TutorContract.objects.create(
            tutor=self.tutor,
            service=TutorContract.Service.COURSE,
            tutor_percent=Decimal("60.00"),
            effective_from=timezone.now() - timedelta(days=1),
            contract_reference="SIGNED-COURSE-001",
        )
        TutorCourseAssignment.objects.create(course=self.course, tutor=self.tutor)

    def checkout(self, accepted=True, key="finance-prod-checkout-001"):
        checkout = create_checkout(
            student=self.student, course=self.course, idempotency_key=key
        )
        return process_payfast_notification(
            {
                "m_payment_id": checkout.payment_reference,
                "pf_payment_id": "FINANCE-COURSE-PF-" + key,
                "payment_status": "COMPLETE",
                "amount_gross": "250.00",
                "custom_str1": str(self.student.supabase_user_id),
                "custom_str2": self.course.slug,
            },
            gateway=VerifiedGateway(accepted),
        )

    def test_verified_payfast_creates_one_immutable_60_40_ledger_entry(self):
        result = self.checkout()
        self.assertTrue(result.accepted, result.reason)
        earning = TutorEarning.objects.get()
        self.assertEqual(earning.tutor_amount, Decimal("150.00"))
        self.assertEqual(earning.academy_amount, Decimal("100.00"))
        self.assertEqual(earning.state, TutorEarning.State.HELD)
        record_course_sale(Payment.objects.get(reference=earning.source_reference))
        self.assertEqual(TutorEarning.objects.count(), 1)
        self.assertEqual(TutorPayout.objects.count(), 0)
        self.contract.tutor_percent = Decimal("50.00")
        self.contract.save()
        earning.refresh_from_db()
        self.assertEqual(earning.tutor_amount, Decimal("150.00"))

    def test_unverified_course_payment_cannot_credit_tutor(self):
        self.assertFalse(self.checkout(False, "finance-prod-rejected-001").accepted)
        self.assertFalse(TutorEarning.objects.exists())

    def make_paid_video(self, *, tutor=None):
        now = timezone.now()
        return VideoRequest.objects.create(
            reference="VRQ-FINANCE-TEST-001",
            idempotency_key="finance-video-prod-001",
            student=self.student,
            assigned_tutor=tutor,
            programme=TutorAvailabilitySlot.Programme.CAPS,
            subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
            level="Grade 12",
            topic="Quadratic equations",
            request_type=VideoRequest.RequestType.CHAPTER_TOPIC,
            amount=Decimal("450.00"),
            currency="ZAR",
            status=VideoRequest.Status.QUEUED,
            provider_reference="PF-VIDEO-FINANCE-TEST-001",
            paid_at=now,
            gateway_verified_at=now,
            queue_entered_at=now,
            ticket_number="AMARIS-VID-FINANCE-001",
        )

    def test_existing_video_checkout_used_without_new_duplicate_order(self):
        TutorContract.objects.create(
            tutor=self.tutor,
            service=TutorContract.Service.VIDEO,
            tutor_percent=Decimal("50.00"),
            effective_from=timezone.now() - timedelta(days=1),
            contract_reference="SIGNED-VIDEO-001",
        )
        request = self.make_paid_video()
        self.assertIsNone(record_existing_video_sale(request))
        self.assertFalse(TutorEarning.objects.exists())
        request.assigned_tutor = self.tutor
        request.save(update_fields=("assigned_tutor", "updated_at"))
        earning = record_existing_video_sale(request)
        self.assertEqual(earning.tutor_amount, Decimal("225.00"))
        self.assertEqual(earning.academy_amount, Decimal("225.00"))
        record_existing_video_sale(request)
        self.assertEqual(TutorEarning.objects.count(), 1)
        self.assertEqual(VideoRequest.objects.count(), 1)
        stats = tutor_dashboard_stats(self.tutor)
        self.assertEqual(stats["categories"]["video"]["count"], 1)
        self.assertEqual(stats["unique_students"], 1)
        self.assertNotIn(self.student.email, repr(stats))
        self.assertNotIn(self.student.first_name, repr(stats))

    def test_rejected_video_states_never_generate_earnings(self):
        TutorContract.objects.create(
            tutor=self.tutor,
            service=TutorContract.Service.VIDEO,
            tutor_percent=Decimal("50.00"),
            effective_from=timezone.now() - timedelta(days=1),
            contract_reference="SIGNED-VIDEO-002",
        )
        request = self.make_paid_video(tutor=self.tutor)
        request.gateway_verified_at = None
        request.save(update_fields=("gateway_verified_at", "updated_at"))
        self.assertIsNone(record_existing_video_sale(request))
        request.gateway_verified_at = timezone.now()
        request.status = VideoRequest.Status.PAYMENT_REVIEW
        request.save(update_fields=("gateway_verified_at", "status", "updated_at"))
        self.assertIsNone(record_existing_video_sale(request))
        self.assertFalse(TutorEarning.objects.exists())

    def test_no_fictional_bank_transfer_receipt(self):
        self.checkout()
        payout = TutorPayout.objects.create(earning=TutorEarning.objects.get())
        self.assertEqual(email_tutor_payout_receipt.run(), 0)
        self.assertEqual(len(mail.outbox), 0)
        payout.state = TutorPayout.State.PAID
        payout.provider_name = "test-bank-provider"
        payout.provider_reference = "TEST-TRANSFER-001"
        payout.confirmed_at = timezone.now()
        payout.bank_last_four = "1234"
        payout.save()
        self.assertEqual(email_tutor_payout_receipt.run(), 1)
        self.assertEqual(email_tutor_payout_receipt.run(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(self.student.email, mail.outbox[0].body)

    def test_bank_number_is_encrypted_and_not_activated_automatically(self):
        with override_settings(TUTOR_BANK_FERNET_KEY=Fernet.generate_key().decode()):
            form = TutorPaymentProfileForm(
                data={
                    "tutor": str(self.tutor.pk),
                    "account_holder": "Finance Tutor",
                    "bank_name": "Test Bank",
                    "branch_code": "000000",
                    "account_number": "1234567890",
                    "is_active": False,
                }
            )
            self.assertTrue(form.is_valid(), form.errors)
            profile = form.save()
            self.assertNotIn("1234567890", profile.encrypted_account_number)
            self.assertEqual(profile.account_last_four, "7890")
            self.assertFalse(profile.is_active)

    def test_earnings_api_requires_verified_tutor_session(self):
        response = self.client.get("/api/v1/tutor/earnings/", secure=True)
        self.assertIn(response.status_code, (401, 403))

    def test_hold_is_not_a_real_payout(self):
        self.checkout()
        earning = TutorEarning.objects.get()
        earning.payment_verified_at = timezone.now() - timedelta(days=8)
        earning.save(update_fields=("payment_verified_at", "updated_at"))
        self.assertEqual(refresh_eligible_earnings(), 1)
        earning.refresh_from_db()
        self.assertEqual(earning.state, TutorEarning.State.READY)
        self.assertEqual(
            TutorPayout.objects.get().state, TutorPayout.State.AWAITING_PROVIDER
        )

    def test_reconciliation_recovers_completed_paid_class_without_double_credit(self):
        paid_at = timezone.now() - timedelta(days=9)
        TutorContract.objects.create(
            tutor=self.tutor,
            service=TutorContract.Service.LIVE_CLASS,
            tutor_percent=Decimal("50.00"),
            effective_from=paid_at - timedelta(days=1),
            contract_reference="SIGNED-CLASS-001",
        )
        slot = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            starts_at=paid_at + timedelta(days=1),
            ends_at=paid_at + timedelta(days=1, hours=2),
            zoom_join_url="https://zoom.example.test/synthetic",
            is_active=True,
        )
        LiveClassBooking.objects.create(
            reference="LVC-FINANCE-COMPLETED-001",
            idempotency_key="finance-completed-001",
            student=self.student,
            slot=slot,
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            topic="Synthetic class",
            amount=Decimal("500.00"),
            currency="ZAR",
            status=LiveClassBooking.Status.COMPLETED,
            paid_at=paid_at,
            gateway_verified_at=paid_at,
            provider_reference="SYNTHETIC-PAYFAST-CLASS-001",
        )
        self.assertEqual(reconcile_tutor_earnings.run(), 1)
        self.assertEqual(reconcile_tutor_earnings.run(), 0)
        earning = TutorEarning.objects.get()
        self.assertEqual(earning.tutor_amount, Decimal("250.00"))
        self.assertEqual(earning.academy_amount, Decimal("250.00"))
        self.assertEqual(earning.service_delivered_at, slot.ends_at)
        self.assertEqual(
            TutorPayout.objects.get().state, TutorPayout.State.AWAITING_PROVIDER
        )
        self.assertEqual(email_tutor_payout_receipt.run(), 0)
        self.assertEqual(len(mail.outbox), 0)
