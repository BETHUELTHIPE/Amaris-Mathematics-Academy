#!/usr/bin/env bash
set -euo pipefail

[[ "$1" =~ ^[a-f0-9]{32}$ && "$2" =~ ^academy-media/videos/cdn-fallback-check-[0-9]+-[0-9]+\.mp4$ && "$3" =~ ^[a-f0-9]{64}$ ]]
task="arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$1"
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$task" --filter label=com.amazonaws.ecs.container-name=backend)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]

docker exec -i "$backend" python - "$2" "$3" <<'PY'
import hashlib
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4

for item in Path("/proc/1/environ").read_bytes().split(b"\0"):
    if item:
        key, _, value = os.fsdecode(item).partition("=")
        os.environ[key] = value


def verify():
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
    django.setup()

    from django.conf import settings
    from django.db import transaction
    from rest_framework.test import APIRequestFactory, force_authenticate

    from content.authentication import SupabaseStudentPrincipal
    from content.models import Course, CourseCategory, CourseModule, Enrollment, Lesson, StudentRecord, VideoAsset
    from content.student_views import StudentLessonView

    media_bucket = "amaris-mathematics-academy-media-stage-110156539003-eu-north-1"
    assert settings.SUPABASE_PROJECT_REF == "atyhhjwwxgzeurnwayay"
    assert settings.ACADEMY_MEDIA_BUCKET == media_bucket
    object_key, expected_sha = sys.argv[1:]
    fixture_id = uuid4().hex
    request_factory = APIRequestFactory()

    with transaction.atomic():
        category = CourseCategory.objects.create(slug=f"cdn-probe-{fixture_id}", name=f"Staging delivery probe {fixture_id}")
        course = Course.objects.create(
            category=category, slug=f"cdn-probe-{fixture_id}", title="Staging delivery probe",
            status=Course.Status.PUBLISHED, price=0,
        )
        module = CourseModule.objects.create(course=course, title="Verification", order=1, is_published=True)
        video = VideoAsset.objects.create(
            title="Synthetic MP4", provider=VideoAsset.Provider.S3, aws_media_key=object_key, is_published=True,
        )
        lesson = Lesson.objects.create(title="Synthetic lesson", slug="verification",
                                       module=module, video=video, is_published=True)
        enrolled, unassigned = [
            StudentRecord.objects.create(
                email=f"cdn-{label}-{fixture_id}@example.test", supabase_user_id=uuid4(),
                first_name="Synthetic", last_name="Check",
            )
            for label in ("enrolled", "unassigned")
        ]
        Enrollment.objects.create(student=enrolled, course=course, status=Enrollment.Status.ACTIVE)

        def issue_request(student=None):
            request = request_factory.get("/private-lesson-probe", secure=True)
            if student:
                force_authenticate(request, user=SupabaseStudentPrincipal(
                    student=student, supabase_user_id=str(student.supabase_user_id), email=student.email,
                ))
            return StudentLessonView.as_view()(request, course_slug=course.slug, lesson_slug=lesson.slug)

        assert issue_request().status_code in (401, 403), "An anonymous API request must be denied."
        assert issue_request(unassigned).status_code == 404, "A non-enrolled student must be denied."
        response = issue_request(enrolled)
        assert response.status_code == 200, "An enrolled student must receive the protected lesson."
        link = urlsplit(response.data["lesson"]["video"]["playback_url"])
        assert link.scheme == "https" and link.hostname == f"{media_bucket}.s3.eu-north-1.amazonaws.com"
        assert link.path == "/" + object_key
        params = parse_qs(link.query)
        assert params.get("X-Amz-Expires") == ["600"] and params.get("X-Amz-Signature")
        transaction.set_rollback(True)

    with urlopen(link.geturl(), timeout=10) as download:
        body = download.read(64_000)
        assert hashlib.sha256(body).hexdigest() == expected_sha
        assert download.headers.get_content_type() == "video/mp4"
    with urlopen(Request(link.geturl(), headers={"Range": "bytes=0-15"}), timeout=10) as download:
        assert download.status == 206 and download.read(17) == body[:16]
        assert download.headers.get("Content-Range") == f"bytes 0-15/{len(body)}"
    try:
        with urlopen(urlunsplit(link._replace(query="")), timeout=10):
            raise AssertionError("The direct video URL must require a signature.")
    except HTTPError as error:
        assert error.code == 403
    print("Enrolled student received a 10-minute private S3 link. Anonymous and non-enrolled requests were denied.")
    print("The signed link returned the exact MP4 and HTTP 206 for a seek. The unsigned object returned HTTP 403.")


try:
    verify()
except HTTPError as error:
    print(f"Lesson video verification stopped at HTTP {error.code}.", file=sys.stderr)
    sys.exit(1)
except AssertionError as error:
    print(f"Lesson video verification assertion failed. {error}", file=sys.stderr)
    sys.exit(1)
except Exception as error:
    print(f"Lesson video verification failed: {type(error).__name__}.", file=sys.stderr)
    sys.exit(1)
PY
