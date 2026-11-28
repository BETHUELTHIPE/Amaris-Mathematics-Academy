#!/usr/bin/env bash
set -euo pipefail
[[ "$1" =~ ^[a-f0-9]{32}$ &&
   "$2" =~ ^academy-media/videos/paid-course-probe-[0-9]+-[0-9]+\.mp4$ &&
   "$3" =~ ^[a-f0-9]{64}$ ]]
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$1" --filter label=com.amazonaws.ecs.container-name=backend)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
docker exec -i "$backend" python - "$2" "$3" <<'PY'
import hashlib
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

for entry in Path("/proc/1/environ").read_bytes().split(b"\0"):
    if entry:
        name, _, value = os.fsdecode(entry).partition("=")
        os.environ[name] = value
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")


def verify():
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection, transaction
    from django.utils import timezone
    from rest_framework.test import APIRequestFactory, force_authenticate
    from content.authentication import SupabaseStudentPrincipal
    from content.models import Course, CourseCategory, CourseModule, Enrollment, Lesson, Payment, StudentRecord, VideoAsset
    from content.services.youtube_copy import youtube_copy_enabled
    from content.student_views import StudentCoursesView, StudentLessonView

    assert settings.SUPABASE_PROJECT_REF == "atyhhjwwxgzeurnwayay"
    bucket = "amaris-mathematics-academy-media-stage-110156539003-eu-north-1"
    assert settings.ACADEMY_MEDIA_BUCKET == bucket
    assert os.environ["RELEASE_GIT_SHA"] == "8f7b34f436c0c1da6cc0bace9c62c89d0712c5d2"
    key, expected_hash = sys.argv[1:]
    suffix = uuid4().hex
    factory = APIRequestFactory()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'content_lesson'::regclass")
            assert cursor.fetchone() == (True,)
            cursor.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'content_youtubelessoncopy'::regclass")
            assert cursor.fetchone() == (True,)
        category = CourseCategory.objects.create(name=f"Paid access probe {suffix}", slug=f"paid-probe-{suffix}")
        course = Course.objects.create(
            category=category, title="Synthetic paid lesson", slug=f"paid-probe-{suffix}", price=1,
            status=Course.Status.PUBLISHED,
        )
        module = CourseModule.objects.create(course=course, order=1, title="Probe", is_published=True)
        video = VideoAsset.objects.create(
            title="Synthetic MP4", provider=VideoAsset.Provider.S3, aws_media_key=key, is_published=True,
        )
        lesson = Lesson.objects.create(
            module=module, title="Paid access check", slug="probe", video=video,
            is_published=True, is_free_preview=True,
        )
        student = StudentRecord.objects.create(
            first_name="Synthetic", last_name="Paid course probe", supabase_user_id=uuid4(),
            email=f"paid-course-probe-{suffix}@example.test",
        )
        Enrollment.objects.create(student=student, course=course, status=Enrollment.Status.ACTIVE)

        def request():
            req = factory.get("/probe", secure=True)
            principal = SupabaseStudentPrincipal(student=student, supabase_user_id=str(student.supabase_user_id), email=student.email)
            force_authenticate(req, user=principal)
            return req

        def open_lesson():
            return StudentLessonView.as_view()(request(), course_slug=course.slug, lesson_slug=lesson.slug)

        assert open_lesson().status_code == 404 and StudentCoursesView.as_view()(request()).data == []
        payment = Payment.objects.create(
            reference=f"paid-course-probe-{suffix}", course=course, student=student,
            provider=Payment.Provider.PAYFAST, amount=1, status=Payment.Status.PAID,
        )
        assert open_lesson().status_code == 404, "An unverified payment was allowed."
        payment.gateway_verified_at = timezone.now()
        payment.save(update_fields=["gateway_verified_at"])
        response = open_lesson()
        assert response.status_code == 200 and response.headers["Cache-Control"] == "private, no-store"
        assert StudentCoursesView.as_view()(request()).data[0]["course"]["slug"] == course.slug
        signed = urlsplit(response.data["lesson"]["video"]["playback_url"])
        assert signed.hostname == f"{bucket}.s3.eu-north-1.amazonaws.com" and signed.path == f"/{key}"
        assert parse_qs(signed.query).get("X-Amz-Signature")
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status"])
        assert open_lesson().status_code == 404 and StudentCoursesView.as_view()(request()).data == []
        transaction.set_rollback(True)

    with urlopen(signed.geturl(), timeout=10) as response:
        assert hashlib.sha256(response.read(64000)).hexdigest() == expected_hash
    with urlopen(Request(signed.geturl(), headers={"Range": "bytes=0-15"}), timeout=10) as response:
        assert response.status == 206 and len(response.read(17)) == 16
    try:
        with urlopen(signed._replace(query="").geturl(), timeout=10):
            raise AssertionError("Unsigned requests could read the video.")
    except HTTPError as error:
        assert error.code == 403
    print("PASS: unpaid, unverified and refunded course access denied. Verified payment unlocked the exact S3 video and seeking.")
    print(f"Private YouTube copying configured: {youtube_copy_enabled()}.")


try:
    verify()
except HTTPError as error:
    raise SystemExit(f"Paid-content proof received HTTP {error.code}.") from None
except Exception as error:
    raise SystemExit(f"Paid-content proof failed: {type(error).__name__}.") from None
PY
