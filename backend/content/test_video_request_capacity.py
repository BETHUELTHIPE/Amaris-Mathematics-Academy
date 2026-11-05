"""100,001-student video request capacity, authorization and concurrency checks.

Synthetic fixture rows contain no real student information or live payments.
This verifies total-record capacity, NOT 100,000 simultaneous uploads.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory
from threading import Barrier

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from content.authentication import SupabaseStudentPrincipal
from content.models import StudentRecord, VideoRequest
from content.services.video_requests import (
    create_video_request_checkout,
    video_request_queue_position,
)


def _synthetic_request(student, index, *, at=None):
    timestamp = at or timezone.now()
    return VideoRequest(
        student=student,
        reference=f"VRQ-CAP-{index:06d}",
        idempotency_key=f"video-capacity-{index:06d}",
        programme="caps",
        subject="mathematics",
        level="Grade 12",
        topic="Differential calculus",
        request_type=VideoRequest.RequestType.CHAPTER_TOPIC,
        instructions="Explain the working with examples.",
        explanation_style="Worked examples",
        preferred_duration_minutes=60,
        amount=Decimal("450.00"),
        status=VideoRequest.Status.QUEUED,
        provider_reference=f"PF-CAP-{index:06d}",
        gateway_verified_at=timestamp,
        paid_at=timestamp,
        queue_entered_at=timestamp,
        ticket_number=f"AMARIS-CAP-{index:06d}",
        invoice_number=f"INV-CAP-{index:06d}",
    )


def _student_client(student):
    client = APIClient()
    client.force_authenticate(
        user=SupabaseStudentPrincipal(
            student=student,
            supabase_user_id=str(student.supabase_user_id),
            email=student.email,
        )
    )
    return client


def _api_checkout_data(key):
    return {
        "programme": "caps",
        "subject": "mathematics",
        "level": "Grade 12",
        "topic": "Integration exam support",
        "request_type": VideoRequest.RequestType.CHAPTER_TOPIC,
        "instructions": "Explain all the integration methods step by step.",
        "explanation_style": "Worked examples",
        "preferred_duration_minutes": 60,
        "idempotency_key": key,
        "documents": [
            SimpleUploadedFile(
                "assignment.pdf",
                b"%PDF-1.4\nsynthetic supporting document\n%%EOF",
                content_type="application/pdf",
            )
        ],
    }


def _private_test_storage(location):
    return override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "student_private": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"location": location},
            },
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    )


class VideoRequestPagingTests(TestCase):
    def setUp(self):
        self.student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="history-student@example.test",
            first_name="History",
            last_name="Student",
        )
        self.other = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="another-history-student@example.test",
            first_name="Other",
            last_name="Student",
        )
        timestamp = timezone.now() - timedelta(hours=1)
        self.items = []
        for i in range(4):
            item = _synthetic_request(self.student, i, at=timestamp + timedelta(seconds=i))
            item.save()
            VideoRequest.objects.filter(pk=item.pk).update(created_at=timestamp + timedelta(seconds=i))
            item.refresh_from_db()
            self.items.append(item)

    def test_student_can_page_private_history_without_large_response(self):
        client = _student_client(self.student)
        first = client.get(reverse("video-request-list"), {"limit": 2}, secure=True)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.data), 2)
        self.assertIn("X-Next-Created-At", first)
        cursor = {
            "limit": 2,
            "before_created_at": first["X-Next-Created-At"],
            "before_id": first["X-Next-Id"],
        }
        second = client.get(reverse("video-request-list"), cursor, secure=True)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.data), 2)
        self.assertNotIn("X-Next-Id", second)
        references = [item["request_reference"] for item in first.data + second.data]
        self.assertEqual(len(set(references)), 4)

    def test_student_cannot_see_another_students_history(self):
        client = _student_client(self.other)
        response = client.get(reverse("video-request-list"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
        denied = client.get(
            reverse("video-request-status", args=[self.items[0].reference]),
            secure=True,
        )
        self.assertEqual(denied.status_code, 404)

    def test_invalid_cursor_and_oversized_page_fail_closed(self):
        client = _student_client(self.student)
        for query in (
            {"limit": 100000},
            {"before_id": str(self.items[0].pk)},
            {"before_created_at": timezone.now().isoformat()},
        ):
            response = client.get(reverse("video-request-list"), query, secure=True)
            self.assertEqual(response.status_code, 400)


class VideoRequestPriorityFairnessTests(TestCase):
    def test_equal_timestamp_priority_has_one_deterministic_first_request(self):
        students = [
            StudentRecord.objects.create(
                supabase_user_id=uuid.uuid4(),
                email=f"queue-student-{i}@example.test",
                first_name="Queue",
                last_name="Student",
            )
            for i in range(3)
        ]
        now = timezone.now()
        priority = []
        for i in range(2):
            item = _synthetic_request(students[i], i + 100, at=now)
            item.priority_paid_at = now
            item.save()
            priority.append(item)
        regular = _synthetic_request(students[2], 102, at=now)
        regular.save()
        ordered = sorted(priority, key=lambda item: item.pk)
        self.assertEqual(
            [video_request_queue_position(item) for item in ordered],
            [1, 2],
        )
        self.assertEqual(video_request_queue_position(regular), 3)


class VideoRequestsOverOneHundredThousandTest(TestCase):
    """Real PostgreSQL records, synthetic identities and no external calls."""

    @classmethod
    def setUpTestData(cls):
        base = timezone.now() - timedelta(days=1)
        cls.total = 100_001
        for start in range(0, cls.total, 1_000):
            stop = min(start + 1_000, cls.total)
            students = [
                StudentRecord(
                    supabase_user_id=uuid.uuid4(),
                    email=f"video-scale-{index:06d}@example.test",
                    first_name="Synthetic",
                    last_name="Student",
                )
                for index in range(start, stop)
            ]
            StudentRecord.objects.bulk_create(students, batch_size=500)
            rows = [
                _synthetic_request(
                    student,
                    index,
                    at=base + timedelta(microseconds=index),
                )
                for index, student in zip(range(start, stop), students, strict=True)
            ]
            VideoRequest.objects.bulk_create(rows, batch_size=500)

    def test_100001st_student_has_paid_request_and_can_start_another_checkout(self):
        self.assertEqual(StudentRecord.objects.count(), 100_001)
        self.assertEqual(VideoRequest.objects.count(), 100_001)
        student = StudentRecord.objects.get(email="video-scale-100000@example.test")
        older = VideoRequest.objects.get(reference="VRQ-CAP-100000")
        self.assertEqual(older.student_id, student.pk)
        self.assertEqual(video_request_queue_position(older), 100_001)

        with (
            TemporaryDirectory() as location,
            override_settings(
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "student_private": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage",
                        "OPTIONS": {"location": location},
                    },
                    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                },
            ),
        ):
            result = create_video_request_checkout(
                student=student,
                programme="caps",
                subject="mathematics",
                level="Grade 12",
                topic="Integration exam support",
                request_type=VideoRequest.RequestType.CHAPTER_TOPIC,
                instructions="Explain all the integration methods step by step.",
                explanation_style="Worked examples",
                preferred_duration_minutes=60,
                idempotency_key="video-last-student-100001",
                documents=[
                    SimpleUploadedFile(
                        "assignment.pdf",
                        b"%PDF-1.4\nsynthetic supporting document\n%%EOF",
                        content_type="application/pdf",
                    )
                ],
            )
            created = VideoRequest.objects.get(reference=result.request_reference)
            self.assertEqual(created.student_id, student.pk)
            self.assertEqual(created.amount, Decimal("450.00"))
            self.assertEqual(created.documents.count(), 1)
            self.assertEqual(result.fields["amount"], "450.00")
            self.assertIn("sandbox.payfast.co.za", result.gateway_url)

    def test_student_api_checkout_and_private_history_with_100001_students(self):
        # Exercise multipart parsing, serializer validation, owner checks and
        # dashboard responses against the large dataset, not just the service.
        with TemporaryDirectory() as location, _private_test_storage(location):
            for index in (0, 50_000, 100_000):
                with self.subTest(student=index + 1):
                    student = StudentRecord.objects.get(email=f"video-scale-{index:06d}@example.test")
                    client = _student_client(student)
                    key = f"video-api-capacity-{index:06d}"
                    response = client.post(
                        reverse("video-request-checkout"),
                        _api_checkout_data(key),
                        format="multipart",
                        secure=True,
                    )
                    self.assertEqual(response.status_code, 201, response.data)
                    self.assertEqual(response["Cache-Control"], "private, no-store")
                    self.assertEqual(response.data["fields"]["amount"], "450.00")
                    self.assertIn("sandbox.payfast.co.za", response.data["gateway_url"])
                    created = VideoRequest.objects.get(reference=response.data["request_reference"])
                    self.assertEqual(created.student_id, student.pk)
                    self.assertEqual(created.status, VideoRequest.Status.PENDING_PAYMENT)
                    self.assertIsNone(created.gateway_verified_at)
                    self.assertIsNone(created.paid_at)
                    self.assertEqual(created.documents.count(), 1)
                    self.assertTrue(
                        created.documents.get().storage_path.startswith(f"{student.supabase_user_id}/video-requests/")
                    )
                    # A retry must return the same order and keep one document.
                    retry = client.post(
                        reverse("video-request-checkout"),
                        _api_checkout_data(key),
                        format="multipart",
                        secure=True,
                    )
                    self.assertEqual(retry.status_code, 201, retry.data)
                    self.assertEqual(retry.data["request_reference"], created.reference)
                    self.assertEqual(created.documents.count(), 1)
                    history = client.get(reverse("video-request-list"), {"limit": 1}, secure=True)
                    self.assertEqual(history.status_code, 200, history.data)
                    self.assertEqual(len(history.data), 1)
                    self.assertEqual(history.data[0]["request_reference"], created.reference)
                    self.assertIn("X-Next-Id", history)
                    other_index = 1 if index == 0 else 0
                    denied = client.get(
                        reverse("video-request-status", args=[f"VRQ-CAP-{other_index:06d}"]),
                        secure=True,
                    )
                    self.assertEqual(denied.status_code, 404)
            self.assertEqual(VideoRequest.objects.count(), 100_004)

    def test_anonymous_student_cannot_submit_to_large_request_dataset(self):
        response = APIClient().post(
            reverse("video-request-checkout"),
            _api_checkout_data("video-anonymous-capacity"),
            format="multipart",
            secure=True,
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(VideoRequest.objects.count(), 100_001)


class ConcurrentVideoRequestIdempotencyTest(TransactionTestCase):
    """Retrying the same key concurrently must create one request and document."""

    def test_same_key_concurrent_checkout_creates_one_request(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL transaction advisory locks required")
        student = StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(),
            email="video-concurrent@example.test",
            first_name="Concurrent",
            last_name="Student",
        )
        start = Barrier(2, timeout=30)
        with (
            TemporaryDirectory() as location,
            override_settings(
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "student_private": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage",
                        "OPTIONS": {"location": location},
                    },
                    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                },
            ),
        ):

            def submit(_):
                close_old_connections()
                try:
                    start.wait()
                    return create_video_request_checkout(
                        student=student,
                        programme="caps",
                        subject="mathematics",
                        level="Grade 12",
                        topic="Algebra equations",
                        request_type=VideoRequest.RequestType.CHAPTER_TOPIC,
                        instructions="Use multiple worked algebra examples.",
                        explanation_style="Worked examples",
                        preferred_duration_minutes=60,
                        idempotency_key="video-duplicate-checkout-001",
                        documents=[
                            SimpleUploadedFile(
                                "notes.pdf",
                                b"%PDF-1.4\nsynthetic notes\n%%EOF",
                                content_type="application/pdf",
                            )
                        ],
                    )
                finally:
                    # ThreadPoolExecutor workers outlive a database transaction.
                    # Explicitly close their thread-local PostgreSQL connection
                    # so Django can drop the ephemeral CI test database.
                    connection.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(submit, (1, 2)))
            self.assertEqual(results[0].request_reference, results[1].request_reference)
            self.assertEqual(
                VideoRequest.objects.filter(idempotency_key="video-duplicate-checkout-001").count(),
                1,
            )
            self.assertEqual(
                VideoRequest.objects.get(idempotency_key="video-duplicate-checkout-001").documents.count(),
                1,
            )

    def test_distinct_students_simultaneous_api_smoke(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL concurrency required")
        # Small CI regression only. The required 50,000-submission acceptance
        # uses load_tests/video_request_burst.mjs on distributed generators.
        count = 16
        students = [
            StudentRecord.objects.create(
                supabase_user_id=uuid.uuid4(),
                email=f"video-parallel-{index:02d}@example.test",
                first_name="Parallel",
                last_name="Student",
            )
            for index in range(count)
        ]
        start = Barrier(count, timeout=30)
        checkout_url = reverse("video-request-checkout")
        with TemporaryDirectory() as location, _private_test_storage(location):

            def submit(index):
                close_old_connections()
                try:
                    client = _student_client(students[index])
                    data = _api_checkout_data(f"video-parallel-api-{index:02d}")
                    start.wait()
                    response = client.post(checkout_url, data, format="multipart", secure=True)
                    self.assertEqual(response.status_code, 201, response.data)
                    return response.data["request_reference"]
                finally:
                    connection.close()

            with ThreadPoolExecutor(max_workers=count) as executor:
                references = list(executor.map(submit, range(count)))
            self.assertEqual(len(set(references)), count)
            self.assertEqual(VideoRequest.objects.count(), count)
            for student, reference in zip(students, references, strict=True):
                request = VideoRequest.objects.get(reference=reference)
                self.assertEqual(request.student_id, student.pk)
                self.assertEqual(request.amount, Decimal("450.00"))
                self.assertEqual(request.status, VideoRequest.Status.PENDING_PAYMENT)
                self.assertIsNone(request.paid_at)
                self.assertEqual(request.documents.count(), 1)
