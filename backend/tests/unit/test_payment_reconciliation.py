import uuid

from django.test import TestCase
from django.utils import timezone

from content.models import Course, CourseCategory, Enrollment, Payment, StudentRecord
from content.services.reconciliation import reconcile_verified_payments


class PaymentReconciliationUnitTests(TestCase):
    def setUp(self):
        category = CourseCategory.objects.create(name="University", slug="university")
        self.course = Course.objects.create(
            category=category,
            title="Calculus I",
            slug="calculus-i-unit",
            short_description="Limits and derivatives",
            description="Introductory calculus",
            curriculum="University",
            academic_level="First year",
            price=1200,
            status=Course.Status.PUBLISHED,
        )
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="unit-payment@example.com",
            first_name="Unit",
            last_name="Student",
        )

    def payment(self, reference: str, verified: bool) -> Payment:
        return Payment.objects.create(
            reference=reference,
            student=self.student,
            course=self.course,
            provider=Payment.Provider.PAYFAST,
            amount=self.course.price,
            status=Payment.Status.PAID,
            paid_at=timezone.now(),
            gateway_verified_at=timezone.now() if verified else None,
            verification_source="payfast_itn" if verified else "",
        )

    def test_unverified_paid_payment_does_not_grant_course_access(self):
        self.payment("UNIT-UNVERIFIED", verified=False)

        run = reconcile_verified_payments()

        self.assertEqual(Enrollment.objects.count(), 0)
        self.assertEqual(run.unresolved_count, 1)

    def test_verified_payment_creates_active_enrollment(self):
        payment = self.payment("UNIT-VERIFIED", verified=True)

        run = reconcile_verified_payments()

        enrollment = Enrollment.objects.get(student=self.student, course=self.course)
        payment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(payment.enrollment_id, enrollment.pk)
        self.assertEqual(run.enrollments_repaired, 1)

    def test_reconciliation_is_idempotent(self):
        self.payment("UNIT-IDEMPOTENT", verified=True)

        first = reconcile_verified_payments()
        second = reconcile_verified_payments()

        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(first.enrollments_repaired, 1)
        self.assertEqual(second.enrollments_repaired, 0)

    def test_cancelled_enrollment_is_never_reactivated(self):
        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status=Enrollment.Status.CANCELLED,
        )
        self.payment("UNIT-CANCELLED", verified=True)

        run = reconcile_verified_payments()

        enrollment = Enrollment.objects.get(student=self.student, course=self.course)
        self.assertEqual(enrollment.status, Enrollment.Status.CANCELLED)
        self.assertEqual(run.unresolved_count, 1)
