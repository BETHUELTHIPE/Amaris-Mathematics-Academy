"""Query budgets and reservation behavior for synthetic tutor dashboards."""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from content.live_class_views import LiveClassSlotView
from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot
from content.tutor_views import TutorDashboardView, _slot_data


class TutorDashboardQueryEfficiencyTests(TestCase):
    def setUp(self):
        self.tutor = get_user_model().objects.create_user(username="query-tutor")
        self.other_tutor = get_user_model().objects.create_user(username="query-other-tutor")
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000881"),
            email="synthetic-query@example.test",
        )
        self.start = timezone.now() + timedelta(days=2)
        self.factory = APIRequestFactory()

    def slot(self, index, *, tutor=None):
        return TutorAvailabilitySlot.objects.create(
            tutor=tutor or self.tutor,
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            starts_at=self.start + timedelta(hours=index * 2),
            ends_at=self.start + timedelta(hours=index * 2 + 1),
            zoom_join_url="https://zoom.example.test/j/123456789",
            is_active=True,
        )

    def booking(self, slot, status):
        return LiveClassBooking.objects.create(
            student=self.student,
            slot=slot,
            reference=f"LCB-query-{slot.pk}-{status}",
            idempotency_key=f"query-booking-{slot.pk}-{status}",
            programme=slot.programme,
            subject=slot.subject,
            level=slot.level,
            topic="Algebra",
            amount=Decimal("250.00"),
            status=status,
            hold_expires_at=timezone.now() - timedelta(minutes=1),
        )

    def dashboard(self):
        request = self.factory.get("/api/v1/tutor/dashboard/", secure=True)
        force_authenticate(request, user=self.tutor)
        return TutorDashboardView.as_view()(request)

    def test_twelve_slots_use_four_queries_and_preserve_reservation_states(self):
        statuses = [value for value, _ in LiveClassBooking.Status.choices]
        expected = {}
        for index in range(12):
            slot = self.slot(index)
            status = statuses[index % len(statuses)]
            self.booking(slot, status)
            # Tutor editing conservatively locks pending/review/completed sales,
            # even when a pending hold has expired. Public availability differs.
            expected[slot.pk] = status in ("pending_payment", "confirmed", "payment_review", "completed")
        foreign = self.slot(40, tutor=self.other_tutor)
        self.booking(foreign, LiveClassBooking.Status.CONFIRMED)

        with self.assertNumQueries(4):
            response = self.dashboard()
            response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["slots"]), 12)
        for item in response.data["slots"]:
            self.assertEqual(item["reserved"], expected[item["id"]])
            self.assertEqual(item["editable"], not expected[item["id"]])
        self.assertEqual(response.data["summary"]["upcoming_slots"], 12)
        self.assertNotIn(foreign.pk, [item["id"] for item in response.data["slots"]])
        for item in response.data["bookings"]:
            if item["status"] not in ("confirmed", "completed"):
                self.assertEqual(item["student_email"], "")
                self.assertEqual(item["zoom_join_url"], "")

    def test_query_budget_is_constant_for_one_slot(self):
        slot = self.slot(0)
        with self.assertNumQueries(4):
            response = self.dashboard()
            response.render()
        self.assertEqual(len(response.data["slots"]), 1)
        self.assertEqual(response.data["slots"][0]["id"], slot.pk)
        self.assertTrue(response.data["slots"][0]["editable"])

    def test_create_update_payload_checks_current_reservations_without_annotation(self):
        slot = self.slot(0)
        with self.assertNumQueries(1):
            self.assertFalse(_slot_data(slot)["reserved"])
        self.booking(slot, LiveClassBooking.Status.CONFIRMED)
        with self.assertNumQueries(1):
            self.assertTrue(_slot_data(slot)["reserved"])

    def availability(self):
        request = self.factory.get("/api/v1/live-classes/slots/", secure=True)
        return LiveClassSlotView.as_view()(request)

    def test_public_slots_use_one_read_query_and_keep_private_links_hidden(self):
        for index in range(12):
            self.slot(index)
        with self.assertNumQueries(1):
            response = self.availability()
            response.render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 12)
        self.assertTrue(all("zoom_join_url" not in item for item in response.data))

    def test_public_availability_applies_expiry_to_the_same_pending_booking(self):
        stale = self.slot(0)
        pending = self.booking(stale, LiveClassBooking.Status.PENDING_PAYMENT)
        cancelled = self.booking(stale, LiveClassBooking.Status.CANCELLED)
        cancelled.hold_expires_at = timezone.now() + timedelta(minutes=10)
        cancelled.save(update_fields=["hold_expires_at"])
        confirmed = self.slot(1)
        self.booking(confirmed, LiveClassBooking.Status.CONFIRMED)
        active = self.slot(2)
        active_booking = self.booking(active, LiveClassBooking.Status.PENDING_PAYMENT)
        active_booking.hold_expires_at = timezone.now() + timedelta(minutes=10)
        active_booking.save(update_fields=["hold_expires_at"])

        with CaptureQueriesContext(connection) as queries:
            response = self.availability()
            response.render()
        self.assertEqual(len(queries), 1)
        self.assertTrue(queries[0]["sql"].lstrip().upper().startswith("SELECT "))
        self.assertEqual([item["id"] for item in response.data], [stale.pk])
        pending.refresh_from_db()
        self.assertEqual(pending.status, LiveClassBooking.Status.PENDING_PAYMENT)

    def test_list_caps_preserve_full_dashboard_summary(self):
        for index in range(125):
            self.slot(index)
        with self.assertNumQueries(4):
            dashboard = self.dashboard()
            dashboard.render()
        self.assertEqual(len(dashboard.data["slots"]), 120)
        self.assertEqual(dashboard.data["summary"]["upcoming_slots"], 125)
        with self.assertNumQueries(1):
            public = self.availability()
            public.render()
        self.assertEqual(len(public.data), 100)
        self.assertLess(public.data[0]["starts_at"], public.data[-1]["starts_at"])
