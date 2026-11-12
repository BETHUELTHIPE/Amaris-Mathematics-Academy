from hashlib import sha256
from io import BytesIO

from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import storages
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from content.services.subscription_reports import MAX_PDF_BYTES, eligible_subscriptions, save_session
from content.student_views import StudentAPIView
from content.subscription_report_models import SubscriptionReport, SubscriptionSession
from content.tutor_views import TutorOnlyAPIView


class SubscriptionReportDownloadView(StudentAPIView):
    @extend_schema(responses={(200, "application/pdf"): bytes})
    def get(self, request, reference):
        sub = get_object_or_404(eligible_subscriptions(), student=self.student, reference=reference)
        report = get_object_or_404(
            SubscriptionReport, subscription=sub, status__in=["ready", "sending", "sent", "review"]
        )
        if not report.pdf_storage_path:
            return Response({"detail": "Your report is being prepared."}, status=409)
        try:
            with storages["student_private"].open(report.pdf_storage_path, "rb") as source:
                data = source.read(MAX_PDF_BYTES + 1)
            if len(data) > MAX_PDF_BYTES or sha256(data).hexdigest() != report.pdf_sha256:
                raise ValueError("archive_integrity")
            document = BytesIO(data)
        except (OSError, ValueError, BotoCoreError, ClientError):
            return Response({"detail": "Your report is temporarily unavailable."}, status=503)
        response = FileResponse(document, as_attachment=True, filename=f"Amaris-learning-report-{sub.reference}.pdf")
        response["X-Content-Type-Options"] = "nosniff"
        return response


class AttendanceInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=["attended", "partial", "absent", "cancelled"])
    joined_at = serializers.DateTimeField(allow_null=True, required=False, default=None)
    left_at = serializers.DateTimeField(allow_null=True, required=False, default=None)
    learning_summary = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    tutor_feedback = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    next_steps = serializers.CharField(max_length=1000, allow_blank=True, required=False)


class PrivateTutorReportAPIView(TutorOnlyAPIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class TutorSubscriptionSessionView(PrivateTutorReportAPIView):
    @extend_schema(request=AttendanceInput, responses=dict)
    def patch(self, request, session_id):
        session = get_object_or_404(
            SubscriptionSession.objects.select_related("subscription"), pk=session_id, tutor=request.user
        )
        values = AttendanceInput(data=request.data)
        values.is_valid(raise_exception=True)
        for field, value in values.validated_data.items():
            setattr(session, field, value)
        try:
            save_session(session, request.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response({"id": session.pk, "status": session.status, "attended_minutes": session.attended_minutes})


class TutorSubscriptionSessionListView(PrivateTutorReportAPIView):
    @extend_schema(responses=dict)
    def get(self, request):
        sessions = SubscriptionSession.objects.filter(tutor=request.user).select_related("subscription__student")
        return Response(
            {
                "results": [
                    {
                        "id": item.pk,
                        "reference": item.subscription.reference,
                        "student": str(
                            item.subscription.student.first_name + " " + item.subscription.student.last_name
                        ).strip(),
                        "starts_at": item.starts_at,
                        "ends_at": item.ends_at,
                        "subject": item.subject,
                        "topic": item.topic,
                        "status": item.status,
                        "learning_summary": item.learning_summary,
                        "tutor_feedback": item.tutor_feedback,
                        "next_steps": item.next_steps,
                        "joined_at": item.joined_at,
                        "left_at": item.left_at,
                    }
                    for item in sessions.order_by("-starts_at")[:100]
                ]
            }
        )
