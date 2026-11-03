"""Isolated CI-only signed checkout matrix for PayFast hosted browser hand-off.

Only the isolated CI database is used. Genuine sandbox callbacks may settle these synthetic orders.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.utils import timezone

from content.models import Course, CourseCategory, LiveClassBooking, Payment, StudentRecord, TutorAvailabilitySlot, VideoRequest
from content.services.live_classes import create_live_class_checkout
from content.services.payments import create_checkout
from content.services.video_requests import create_video_request_checkout

if os.environ.get("PAYFAST_MODE") != "sandbox" or os.environ.get("SUPABASE_DATABASE_REQUIRED") != "false":
    raise SystemExit("Sandbox-only test: production settings are forbidden.")
if any(term in os.environ.get("DATABASE_URL", "") for term in ("supabase.co", "render.com")):
    raise SystemExit("Sandbox-only test: refuse live database.")
if not os.environ.get("PAYFAST_MERCHANT_ID") or not os.environ.get("PAYFAST_MERCHANT_KEY"):
    raise SystemExit("Sandbox merchant secrets missing.")

key = "wallet-" + os.environ["GITHUB_RUN_ID"] + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
student = StudentRecord.objects.create(
    supabase_user_id=uuid.uuid4(), email="sandbox-buyer@example.invalid",
    first_name="Amaris", last_name="Sandbox",
)
tutor = get_user_model().objects.create_user(username="ci-wallet-tutor", email="tutor@example.invalid")
category = CourseCategory.objects.create(name="Synthetic Wallet Testing",slug="synthetic-wallet-testing")
course = Course.objects.create(
    category=category, title="Synthetic Test Course", slug="synthetic-wallet-course",
    short_description="Sandbox only", description="Never enroll a real learner",
    curriculum="Synthetic", academic_level="Test", price=Decimal("950.00"),
    status=Course.Status.PUBLISHED,
)
matrix = []

def add(kind, expected, session):
    amount=session.fields["amount"]
    assert amount == expected, (kind, amount, expected)
    assert session.gateway_url == "https://sandbox.payfast.co.za/eng/process"
    matrix.append({"kind":kind,"amount":amount,"url":session.gateway_url,"fields":session.fields,"reference":session.fields["m_payment_id"]})
    print("SANDBOX_CHECKOUT_CREATED=" + kind + ":" + amount)

checkout = create_checkout(student=student,course=course,idempotency_key=key+"-course")
add("course_950", "950.00", checkout)

for hours in (1,2,3):
    start=(timezone.now()+timedelta(days=3+hours)).replace(second=0,microsecond=0)
    slot=TutorAvailabilitySlot.objects.create(
        tutor=tutor, programme=TutorAvailabilitySlot.Programme.CAPS,
        subject=TutorAvailabilitySlot.Subject.MATHEMATICS,level="Grade 12",
        starts_at=start,ends_at=start+timedelta(hours=hours),
        zoom_join_url="https://zoom.example.invalid/j/123456789",
        is_active=True,
    )
    sess=create_live_class_checkout(student=student,slot=slot,topic="Calculus exam revision",idempotency_key=key+"-"+str(hours)+"hr")
    add(f"live_class_{hours}h",f"{hours*250:.2f}",sess)

for request_type, amount in (("chapter_topic","450.00"),("previous_assignment","450.00"),("previous_exam","1800.00"),("complete_content","1800.00")):
    sess=create_video_request_checkout(
        student=student,programme="caps",subject="mathematics",level="Grade 12",
        topic="Functions",request_type=request_type,instructions="Synthetic sandbox only",
        explanation_style="Worked examples",preferred_duration_minutes=60,
        idempotency_key=key+"-"+request_type,documents=(),
    )
    add("video_"+request_type,amount,sess)

assert Payment.objects.count()==1 and Payment.objects.get().status==Payment.Status.PENDING
assert LiveClassBooking.objects.count()==3 and not LiveClassBooking.objects.exclude(status=LiveClassBooking.Status.PENDING_PAYMENT).exists()
assert VideoRequest.objects.count()==4 and not VideoRequest.objects.exclude(status=VideoRequest.Status.PENDING_PAYMENT).exists()
Path("/tmp/amaris-hosted-checkouts.json").write_text(json.dumps(matrix),encoding="utf-8")
print("HOSTED_SANDBOX_MATRIX_READY=8")
