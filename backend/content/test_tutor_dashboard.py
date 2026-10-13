"""Isolated tutor portal tests. No live Zoom, Supabase or PayFast requests."""

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentAuthentication
from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot


class TutorSelfServiceTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Tutors")
        model = get_user_model()
        self.tutor = model.objects.create_user(username="tutor-a", email="tutor.a@example.test")
        self.tutor.groups.add(self.group)
        self.other_tutor = model.objects.create_user(username="tutor-b", email="tutor.b@example.test")
        self.other_tutor.groups.add(self.group)
        self.student_user = model.objects.create_user(username="student", email="student@example.test")
        self.client = APIClient()
        self.starts_at = (timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)

    def payload(self, email="tutor.a@example.test", verified=True):
        return {
            "id": str(uuid.UUID("00000000-0000-4000-8000-000000000010")),
            "email": email,
            "email_confirmed_at": "2026-10-01T12:00:00Z" if verified else None,
        }

    def request(self, method, route, *, data=None, email="tutor.a@example.test", verified=True):
        with patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=self.payload(email, verified)):
            return getattr(self.client, method)(
                route,
                data=data,
                format="json",
                HTTP_AUTHORIZATION="Bearer synthetic-unit-test-token",
                secure=True,
            )

    def slot_data(self, *, hours=2, starts_at=None):
        return {
            "programme": "caps",
            "subject": "mathematics",
            "level": "Grade 12",
            "starts_at": (starts_at or self.starts_at).isoformat(),
            "duration_hours": hours,
            "zoom_join_url": "https://zoom.example.test/j/123456789",
            "is_active": True,
        }

    def create(self, *, hours=2, starts_at=None, email="tutor.a@example.test"):
        return self.request(
            "post", reverse("tutor-slot-create"), data=self.slot_data(hours=hours, starts_at=starts_at), email=email
        )

    def test_requires_verified_supabase_account_and_explicit_tutors_group(self):
        result = self.client.get(reverse("tutor-dashboard"), secure=True)
        self.assertEqual(result.status_code, 401)
        unverified = self.request("get", reverse("tutor-dashboard"), verified=False)
        self.assertEqual(unverified.status_code, 401)
        student = self.request("get", reverse("tutor-dashboard"), email="student@example.test")
        self.assertEqual(student.status_code, 401)
        # Django superusers do not automatically become tutors without approval.
        admin = get_user_model().objects.create_superuser(
            username="root", email="root@example.test", password="synthetic-test-only-password"
        )
        self.assertTrue(admin.is_superuser)
        root = self.request("get", reverse("tutor-dashboard"), email="root@example.test")
        self.assertEqual(root.status_code, 401)
        allowed = self.request("get", reverse("tutor-dashboard"))
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["tutor"]["email"], self.tutor.email)
        self.assertEqual(StudentRecord.objects.count(), 0)

    def test_ambiguous_approved_email_is_denied(self):
        duplicate = get_user_model().objects.create_user(username="duplicate", email=self.tutor.email)
        duplicate.groups.add(self.group)
        response = self.request("get", reverse("tutor-dashboard"))
        self.assertEqual(response.status_code, 401)

    def test_one_two_and_three_hours_have_correct_prices(self):
        for hours in (1, 2, 3):
            with self.subTest(hours=hours):
                result = self.create(hours=hours, starts_at=self.starts_at + timedelta(days=hours))
                self.assertEqual(result.status_code, 201, result.data)
                self.assertEqual(result.data["duration_hours"], hours)
                self.assertEqual(result.data["price"], f"{hours * 250:.2f}")
                stored = TutorAvailabilitySlot.objects.get(pk=result.data["id"])
                self.assertEqual(stored.ends_at - stored.starts_at, timedelta(hours=hours))
        public = self.client.get(reverse("live-class-slots"), secure=True).json()
        self.assertEqual(sorted(item["price"] for item in public), ["250.00", "500.00", "750.00"])
        self.assertTrue(all("zoom_join_url" not in item for item in public))

    def test_tutor_can_edit_and_deactivate_only_own_unbooked_slots(self):
        created = self.create()
        self.assertEqual(created.status_code, 201)
        url = reverse("tutor-slot-update", args=[created.data["id"]])
        other = self.request("patch", url, data={"duration_hours": 3}, email="tutor.b@example.test")
        self.assertEqual(other.status_code, 404)
        # A malicious tutor_id value must not reassign the owner's slot.
        modified = self.request("patch", url, data={"duration_hours": 3, "tutor_id": self.other_tutor.id})
        self.assertEqual(modified.status_code, 200, modified.data)
        self.assertEqual(modified.data["price"], "750.00")
        slot = TutorAvailabilitySlot.objects.get(pk=created.data["id"])
        self.assertEqual(slot.tutor_id, self.tutor.pk)
        inactive = self.request("patch", url, data={"is_active": False})
        self.assertEqual(inactive.status_code, 200, inactive.data)
        self.assertFalse(inactive.data["is_active"])

    def test_reject_invalid_hours_overlap_and_past_start(self):
        for hours in (0, 25, -1, 1.5):
            with self.subTest(hours=hours):
                result = self.create(hours=hours)
                self.assertEqual(result.status_code, 400)
        past = self.create(starts_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(past.status_code, 400)
        first = self.create(hours=3)
        self.assertEqual(first.status_code, 201, first.data)
        overlap = self.create(hours=1, starts_at=self.starts_at + timedelta(hours=2))
        self.assertEqual(overlap.status_code, 400)
        adjoining = self.create(hours=1, starts_at=self.starts_at + timedelta(hours=3))
        self.assertEqual(adjoining.status_code, 201, adjoining.data)

    def test_reserved_booking_cannot_be_modified_or_disabled_and_private_details_are_hidden(self):
        slot_result = self.create(hours=3)
        slot = TutorAvailabilitySlot.objects.get(pk=slot_result.data["id"])
        student = StudentRecord.objects.create(
            supabase_user_id=uuid.UUID("00000000-0000-4000-8000-000000000301"),
            first_name="Private",
            last_name="Student",
            email="private.student@example.test",
        )
        booking = LiveClassBooking.objects.create(
            reference="LCB-tutor-dashboard-1",
            idempotency_key="tutor-dashboard-reserved-1",
            student=student,
            slot=slot,
            programme=slot.programme,
            subject=slot.subject,
            level=slot.level,
            topic="Functions",
            amount=Decimal("750.00"),
            status=LiveClassBooking.Status.PENDING_PAYMENT,
        )
        data = self.request("get", reverse("tutor-dashboard")).data
        self.assertEqual(len(data["bookings"]), 1)
        self.assertFalse(data["bookings"][0]["student_email"])
        self.assertFalse(data["bookings"][0]["zoom_join_url"])
        self.assertEqual(data["bookings"][0]["amount"], "750.00")
        patch_url = reverse("tutor-slot-update", args=[slot.id])
        refused = self.request("patch", patch_url, data={"is_active": False})
        self.assertEqual(refused.status_code, 400)
        refused = self.request("patch", patch_url, data={"duration_hours": 2})
        self.assertEqual(refused.status_code, 400)
        booking.status = LiveClassBooking.Status.CONFIRMED
        booking.save(update_fields=["status"])
        confirmed = self.request("get", reverse("tutor-dashboard")).data
        self.assertEqual(confirmed["bookings"][0]["student_email"], student.email)
        self.assertEqual(confirmed["bookings"][0]["student_name"], "Private Student")
        other = self.request("get", reverse("tutor-dashboard"), email="tutor.b@example.test").data
        self.assertEqual(other["slots"], [])
        self.assertEqual(other["bookings"], [])

    def test_fake_github_acceptance_header_never_approves_tutor(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer forged-token",
            HTTP_X_AMARIS_ACCEPTANCE="github-actions",
        )
        # Tutor auth never interprets GitHub acceptance bypass headers.
        with patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=self.payload("student@example.test")):
            response = self.client.get(reverse("tutor-dashboard"), secure=True)
        self.assertEqual(response.status_code, 401)
