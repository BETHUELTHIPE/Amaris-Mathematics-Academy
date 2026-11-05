"""Run against the current production backend in an isolated CI database."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from content.models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot, VideoRequest
from content.services.live_classes import create_live_class_checkout
from content.services.video_requests import create_video_request_checkout


class SchoolBookingGradeTests(TestCase):
    def setUp(self):
        self.tutor = get_user_model().objects.create_user(username="school-grade-tutor")
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email="synthetic@example.test", first_name="Synthetic"
        )

    @patch.dict("os.environ", {"PAYFAST_MODE": "sandbox"})
    def test_caps_and_ieb_grade_7_to_12_live_bookings_preserve_grade_and_topic(self):
        for index, (programme, grade) in enumerate(
            (programme, grade) for programme in ("caps", "ieb") for grade in range(7, 13)
        ):
            with self.subTest(programme=programme, grade=grade):
                level = f"Grade {grade}"
                topic = "Whole-number calculations" if grade < 10 else "Equations and inequalities"
                start = timezone.now() + timedelta(days=index + 2)
                slot = TutorAvailabilitySlot.objects.create(
                    tutor=self.tutor,
                    programme=programme,
                    subject="mathematics",
                    level=level,
                    starts_at=start,
                    ends_at=start + timedelta(hours=1),
                    zoom_join_url="https://zoom.example.test/j/synthetic",
                    is_active=True,
                )
                response = self.client.get(
                    reverse("live-class-slots"),
                    {"programme": programme, "subject": "mathematics", "level": level},
                    secure=True,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()[0]["level"], level)
                session = create_live_class_checkout(
                    student=self.student, slot=slot, topic=topic, idempotency_key=f"grade-live-{index:03d}"
                )
                booking = LiveClassBooking.objects.get(reference=session.booking_reference)
                self.assertEqual((booking.programme, booking.level, booking.topic), (programme, level, topic))
                self.assertEqual(booking.status, LiveClassBooking.Status.PENDING_PAYMENT)

    @patch.dict("os.environ", {"PAYFAST_MODE": "sandbox"})
    def test_caps_and_ieb_grade_7_to_12_video_requests_preserve_grade_and_custom_chapter(self):
        for index, (programme, grade) in enumerate(
            (programme, grade) for programme in ("caps", "ieb") for grade in range(7, 13)
        ):
            with self.subTest(programme=programme, grade=grade):
                level = f"Grade {grade}"
                topic = f"School chapter {grade}, assignment question 4"
                session = create_video_request_checkout(
                    student=self.student,
                    programme=programme,
                    subject="mathematics",
                    level=level,
                    topic=topic,
                    request_type="chapter_topic",
                    instructions="Synthetic recording request",
                    explanation_style="Worked examples",
                    preferred_duration_minutes=60,
                    idempotency_key=f"grade-video-{index:03d}",
                    documents=(),
                )
                request = VideoRequest.objects.get(reference=session.request_reference)
                self.assertEqual((request.programme, request.level, request.topic), (programme, level, topic))
                self.assertEqual(request.status, VideoRequest.Status.PENDING_PAYMENT)
