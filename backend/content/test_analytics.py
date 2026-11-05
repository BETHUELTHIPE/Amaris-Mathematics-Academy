"""Owner isolation, verified-money semantics, SAST windows and bounded analytics queries."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentAuthentication, SupabaseStudentPrincipal
from content.models import (
    Course,
    CourseCategory,
    Enrollment,
    LiveClassBooking,
    Payment,
    StudentRecord,
    TutorAvailabilitySlot,
)
from content.services.analytics import student_analytics
from content.tutor_finance_models import TutorContract, TutorEarning, TutorPayout

NOW = datetime(2026, 11, 5, 8, tzinfo=UTC)


class AnalyticsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = patch("content.services.analytics.timezone.now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="private.student@example.test",
            first_name="Private",
            last_name="Student",
        )
        self.other = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="other.student@example.test", first_name="Other", last_name="Student"
        )
        self.course = Course.objects.create(
            category=CourseCategory.objects.create(name="Mathematics", slug="maths"),
            title="Calculus",
            slug="calculus",
            price=Decimal("100.00"),
        )
        group = Group.objects.create(name="Tutors")
        self.tutor = get_user_model().objects.create_user(username="tutor-a", email="private.tutor@example.test")
        self.tutor.groups.add(group)
        self.other_tutor = get_user_model().objects.create_user(username="tutor-b", email="other.tutor@example.test")
        self.other_tutor.groups.add(group)
        self.client = APIClient()

    def student_login(self, student=None):
        actor = student or self.student
        self.client.force_authenticate(
            SupabaseStudentPrincipal(student=actor, supabase_user_id=str(actor.supabase_user_id), email=actor.email)
        )

    def pay(self, reference, *, student=None, amount="100.00", verified=True, status="paid", at=None, currency="ZAR"):
        return Payment.objects.create(
            reference=reference,
            student=student or self.student,
            course=self.course,
            provider="payfast",
            amount=Decimal(amount),
            currency=currency,
            status=status,
            paid_at=at or NOW,
            gateway_verified_at=NOW if verified else None,
        )

    def metrics(self, data):
        return {item["key"]: item for item in data["metrics"]}

    def test_student_scope_verified_money_and_no_private_identifiers(self):
        self.pay("own-paid")
        self.pay("other-paid", student=self.other, amount="999.00")
        self.pay("pending-unverified", verified=False)
        self.pay("refunded", status="refunded")
        self.pay("other-currency", currency="USD")
        Enrollment.objects.create(student=self.student, course=self.course, status="active", progress_percent=40)
        self.student_login()
        response = self.client.get(reverse("student-analytics"), secure=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("Authorization", response["Vary"])
        metrics = self.metrics(response.data)
        self.assertEqual(metrics["paid_services"]["total"], 1)
        self.assertEqual(metrics["spending"]["total"], 10000)
        self.assertEqual(response.data["progress"]["percent"], 40)
        self.assertEqual(len(metrics["spending"]["series"]), 30)
        for private in (
            self.student.email,
            self.other.email,
            "own-paid",
            "other-paid",
            "student_id",
            "access_token",
            "bank_account",
        ):
            self.assertNotIn(private, str(response.data))

    def test_sast_midnight_boundaries_and_future_payments(self):
        self.pay("before-start", at=datetime(2026, 10, 29, 21, 59, tzinfo=UTC))
        self.pay("at-start", at=datetime(2026, 10, 29, 22, tzinfo=UTC))
        self.pay("sast-today", at=datetime(2026, 11, 4, 23, 30, tzinfo=UTC))
        self.pay("future", at=NOW + timedelta(minutes=1))
        self.student_login()
        response = self.client.get(reverse("student-analytics"), {"days": 7}, secure=True)
        metrics = self.metrics(response.data)
        self.assertEqual(response.data["period"]["start"], "2026-10-30")
        self.assertEqual(metrics["paid_services"]["total"], 2)
        self.assertEqual(metrics["paid_services"]["series"][0]["value"], 1)
        self.assertEqual(metrics["paid_services"]["series"][-1]["value"], 1)

    def test_rejects_unbounded_filters_foreign_identity_and_writes(self):
        self.student_login()
        for query in (
            {"days": 100000},
            {"days": "invalid"},
            {"student_id": self.other.pk},
            {"tutor_id": self.other_tutor.pk},
        ):
            response = self.client.get(reverse("student-analytics"), query, secure=True)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(reverse("student-analytics"), {}, secure=True).status_code, 405)

    def test_empty_account_is_measured_zero_not_another_persons_data(self):
        self.pay("not-owned")
        self.student_login(self.other)
        response = self.client.get(reverse("student-analytics"), {"days": 90}, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["total"] == 0 for item in response.data["metrics"]))
        self.assertEqual(response.data["progress"]["total"], 0)

    def test_anonymous_and_unverified_identities_are_denied(self):
        self.assertEqual(self.client.get(reverse("student-analytics"), secure=True).status_code, 401)
        self.assertEqual(self.client.get(reverse("tutor-analytics"), secure=True).status_code, 401)
        with patch.object(
            SupabaseStudentAuthentication,
            "_validate_token",
            return_value={
                "id": str(self.student.supabase_user_id),
                "email": self.student.email,
                "email_confirmed_at": None,
            },
        ):
            response = self.client.get(
                reverse("student-analytics"), HTTP_AUTHORIZATION="Bearer synthetic-test", secure=True
            )
            self.assertEqual(response.status_code, 401)

    def test_1000_payments_are_aggregated_in_constant_queries_and_bounded_payload(self):
        Payment.objects.bulk_create(
            [
                Payment(
                    reference=f"scale-{i}",
                    student=self.student,
                    course=self.course,
                    provider="payfast",
                    amount=Decimal("1.00"),
                    currency="ZAR",
                    status="paid",
                    paid_at=NOW,
                    gateway_verified_at=NOW,
                )
                for i in range(1000)
            ]
        )
        with self.assertNumQueries(9):
            result = student_analytics(self.student, 30)
        self.assertEqual(self.metrics(result)["paid_services"]["total"], 1000)
        self.assertEqual(len(self.metrics(result)["paid_services"]["series"]), 30)

    def test_tutor_scope_payout_confirmation_and_completion_semantics(self):
        contract = TutorContract.objects.create(
            tutor=self.tutor, service="course", tutor_percent=60, contract_reference="private-contract"
        )

        def earning(reference, tutor, *, state="held"):
            return TutorEarning.objects.create(
                tutor=tutor,
                contract=contract,
                service="course",
                source_reference=reference,
                service_label="Private sale",
                gross=100,
                tutor_percent=60,
                tutor_amount=60,
                academy_amount=40,
                state=state,
                payment_verified_at=NOW,
            )

        own = earning("own-source", self.tutor, state="paid")
        earning("other-source", self.other_tutor)
        earning("reversed-source", self.tutor, state="reversed")
        unconfirmed = earning("unconfirmed-source", self.tutor)
        TutorPayout.objects.create(earning=own, state="paid", provider_reference="private-bank-ref", confirmed_at=NOW)
        TutorPayout.objects.create(earning=unconfirmed, state="paid", provider_reference="", confirmed_at=None)
        slot = TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            starts_at=NOW - timedelta(days=1),
            ends_at=NOW - timedelta(days=1) + timedelta(hours=2),
            is_active=False,
        )
        LiveClassBooking.objects.create(
            student=self.student,
            slot=slot,
            reference="private-booking",
            idempotency_key="private-booking-key",
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            topic="Functions",
            amount=500,
            status="completed",
            paid_at=NOW,
            gateway_verified_at=NOW,
        )
        self.client.force_authenticate(self.tutor)
        response = self.client.get(reverse("tutor-analytics"), secure=True)
        self.assertEqual(response.status_code, 200, response.data)
        metrics = self.metrics(response.data)
        self.assertEqual(metrics["earnings"]["total"], 12000)
        self.assertEqual(metrics["payouts"]["total"], 6000)
        self.assertEqual(metrics["lesson_hours"]["total"], 2)
        self.assertEqual(response.data["progress"]["percent"], 100)
        self.assertNotIn("private-bank-ref", str(response.data))
        self.assertNotIn(self.student.email, str(response.data))

    def test_student_session_does_not_grant_tutor_analytics(self):
        with patch.object(
            SupabaseStudentAuthentication,
            "_validate_token",
            return_value={
                "id": str(self.student.supabase_user_id),
                "email": self.student.email,
                "email_confirmed_at": NOW.isoformat(),
            },
        ):
            response = self.client.get(
                reverse("tutor-analytics"), HTTP_AUTHORIZATION="Bearer synthetic-test", secure=True
            )
        self.assertEqual(response.status_code, 401)
