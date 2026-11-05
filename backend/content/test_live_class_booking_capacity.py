"""Large-population and burst-safety checks for live tutoring bookings.

All students, tutors, sessions and payments in this file are synthetic.
Only the GitHub Actions test PostgreSQL database is changed.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot
from content.services.live_classes import PaymentSecurityError, create_live_class_checkout
from content.tasks import deliver_live_class_confirmation, deliver_live_class_reminder


def create_slot(tutor, number=0, *, start=None):
    starts = start or timezone.now() + timedelta(hours=2 + number)
    return TutorAvailabilitySlot.objects.create(
        tutor=tutor,
        programme=TutorAvailabilitySlot.Programme.CAPS,
        subject=TutorAvailabilitySlot.Subject.MATHEMATICS,
        level="Grade 12",
        starts_at=starts,
        ends_at=starts + timedelta(hours=1),
        zoom_join_url="https://zoom.example.test/j/123456",
    )


class ScalableAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tutor = get_user_model().objects.create_user(
            username="capacity-tutor", email="capacity-tutor@example.test"
        )
        cls.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="capacity-student@example.test",
            first_name="Capacity",
            last_name="Student",
        )
        cls.slot = create_slot(cls.tutor)

    def test_get_does_not_write_to_booking_table_while_releasing_expired_hold_for_search(self):
        held = LiveClassBooking.objects.create(
            reference="LCB-READ-ONLY",
            idempotency_key="availability-readonly-001",
            student=self.student,
            slot=self.slot,
            programme=self.slot.programme,
            subject=self.slot.subject,
            level=self.slot.level,
            topic="Calculus",
            amount=Decimal("250.00"),
            status=LiveClassBooking.Status.PENDING_PAYMENT,
            hold_expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = self.client.get(reverse("live-class-slots"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(self.slot.pk), [row["id"] for row in response.json()])
        held.refresh_from_db()
        self.assertEqual(held.status, LiveClassBooking.Status.PENDING_PAYMENT)

    def test_keyset_paging_is_stable_when_many_slots_exist(self):
        second = create_slot(self.tutor, 2)
        first = self.client.get(
            reverse("live-class-slots"), {"limit": 1}, secure=True
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual([s["id"] for s in first.json()], [str(self.slot.pk)])
        next_page = self.client.get(
            reverse("live-class-slots"),
            {
                "limit": 1,
                "after_start": self.slot.starts_at.isoformat(),
                "after_id": self.slot.pk,
            },
            secure=True,
        )
        self.assertEqual(next_page.status_code, 200)
        self.assertEqual([s["id"] for s in next_page.json()], [str(second.pk)])
        invalid = self.client.get(
            reverse("live-class-slots"), {"after_id": self.slot.pk}, secure=True
        )
        self.assertEqual(invalid.status_code, 400)

    def test_all_levels_are_discoverable_beyond_the_first_hundred_slots(self):
        TutorAvailabilitySlot.objects.bulk_create(
            [
                TutorAvailabilitySlot(
                    tutor=self.tutor,
                    programme=self.slot.programme,
                    subject=self.slot.subject,
                    level="Grade 12",
                    starts_at=self.slot.starts_at + timedelta(hours=i + 1),
                    ends_at=self.slot.ends_at + timedelta(hours=i + 1),
                    zoom_join_url=self.slot.zoom_join_url,
                )
                for i in range(110)
            ]
        )
        TutorAvailabilitySlot.objects.create(
            tutor=self.tutor,
            programme=self.slot.programme,
            subject=self.slot.subject,
            level="Grade 9",
            starts_at=self.slot.starts_at + timedelta(hours=112),
            ends_at=self.slot.ends_at + timedelta(hours=112),
            zoom_join_url=self.slot.zoom_join_url,
        )
        response = self.client.get(
            reverse("live-class-levels"),
            {"programme": "caps", "subject": "mathematics"},
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ["Grade 12", "Grade 9"])

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        LIVE_CLASS_NOTIFICATION_BATCH_SIZE=2,
    )
    def test_notification_batches_process_multiple_students_without_duplicate_emails(self):
        from django.core import mail

        now = timezone.now()
        for n in range(3):
            slot = create_slot(self.tutor, 10 + n)
            student = StudentRecord.objects.create(
                supabase_user_id=uuid.uuid4(),
                email=f"batch-student-{n}@example.test",
                first_name="Batch",
                last_name=str(n),
            )
            LiveClassBooking.objects.create(
                reference=f"LCB-BATCH-{n}",
                idempotency_key=f"batch-notify-{n:08d}",
                student=student,
                slot=slot,
                programme=slot.programme,
                subject=slot.subject,
                level=slot.level,
                topic="Algebra",
                amount=Decimal("250.00"),
                status=LiveClassBooking.Status.CONFIRMED,
                paid_at=now,
            )
        self.assertEqual(deliver_live_class_confirmation.run(), 2)
        self.assertEqual(deliver_live_class_confirmation.run(), 1)
        self.assertEqual(deliver_live_class_confirmation.run(), 0)
        self.assertEqual(len(mail.outbox), 3)

        for booking in LiveClassBooking.objects.filter(reference__startswith="LCB-BATCH-"):
            starts = now + timedelta(minutes=20)
            TutorAvailabilitySlot.objects.filter(pk=booking.slot_id).update(
                starts_at=starts + timedelta(minutes=int(booking.reference[-1])),
                ends_at=starts + timedelta(minutes=int(booking.reference[-1]) + 60),
            )
        self.assertEqual(deliver_live_class_reminder.run(), 2)
        self.assertEqual(deliver_live_class_reminder.run(), 1)
        self.assertEqual(deliver_live_class_reminder.run(), 0)
        self.assertEqual(len(mail.outbox), 6)


class MoreThanOneHundredThousandStudentsTest(TestCase):
    """Validate the high-ID student is bookable after 100,001 registrations."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = get_user_model().objects.create_user(username="big-student-test-tutor")
        cls.slot = create_slot(cls.tutor, 5)
        for start in range(0, 100_001, 2_000):
            students = [
                StudentRecord(
                    supabase_user_id=uuid.uuid4(),
                    email=f"scale-student-{i:06d}@example.test",
                    first_name="Synthetic",
                    last_name="Student",
                )
                for i in range(start, min(start + 2_000, 100_001))
            ]
            StudentRecord.objects.bulk_create(students, batch_size=1_000)

    def test_student_number_100001_can_reserve_a_real_slot(self):
        self.assertEqual(StudentRecord.objects.count(), 100_001)
        last_student = StudentRecord.objects.get(
            email="scale-student-100000@example.test"
        )
        checkout = create_live_class_checkout(
            student=last_student,
            slot=self.slot,
            topic="Mathematics tutorial",
            idempotency_key="scale-student-100001-checkout",
        )
        self.assertIn("sandbox.payfast.co.za", checkout.gateway_url)
        self.assertEqual(checkout.fields["amount"], "250.00")
        self.assertEqual(
            LiveClassBooking.objects.get(reference=checkout.booking_reference).student_id,
            last_student.pk,
        )


class ConcurrentSingleSlotBookingTest(TransactionTestCase):
    """Two concurrent students cannot purchase the same one-to-one tutor slot."""

    def test_competing_students_only_get_one_active_hold(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locking is required for this concurrency check.")
        tutor = get_user_model().objects.create_user(username="parallel-booking-tutor")
        slot = create_slot(tutor, 30)
        students = [
            StudentRecord.objects.create(
                supabase_user_id=uuid.uuid4(),
                email=f"parallel-student-{i}@example.test",
                first_name="Parallel",
                last_name="Student",
            )
            for i in range(2)
        ]

        def reserve(i):
            close_old_connections()
            try:
                create_live_class_checkout(
                    student=students[i],
                    slot=slot,
                    topic="Concurrent algebra",
                    idempotency_key=f"parallel-booking-key-{i:08d}",
                )
                return "reserved"
            except PaymentSecurityError:
                return "unavailable"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(reserve, range(2)))
        self.assertCountEqual(outcomes, ["reserved", "unavailable"])
        self.assertEqual(
            LiveClassBooking.objects.filter(
                slot=slot, status=LiveClassBooking.Status.PENDING_PAYMENT
            ).count(),
            1,
        )
