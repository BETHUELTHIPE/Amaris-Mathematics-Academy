"""Isolated development-only matrix for actual PayFast sandbox hosted checkouts.

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
    curriculum="Synthetic", academic_level="Test", price=Decimal("20.00"),
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
add("course_probe", "20.00", checkout)


assert Payment.objects.count()==1 and Payment.objects.get().status==Payment.Status.PENDING
Path("/tmp/amaris-all-payfast-bookings.json").write_text(json.dumps(matrix),encoding="utf-8")
print("SANDBOX_CHECKOUT_MATRIX_READY=1")
