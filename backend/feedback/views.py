from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from content.authentication import SupabaseStudentAuthentication
from content.models import LiveClassBooking, Enrollment, Payment
from .models import HappyForm
from .tasks import deliver_happy_form

class HappyFormThrottle(UserRateThrottle):
    scope = "feedback"

class HappyFormSerializer(serializers.Serializer):
    service = serializers.ChoiceField(choices=HappyForm.Service.choices)
    service_reference = serializers.CharField(max_length=100)
    overall_rating = serializers.IntegerField(min_value=1, max_value=5)
    tutor_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    comments = serializers.CharField(max_length=1000, required=False, allow_blank=True, trim_whitespace=True)

class HappyFormView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (HappyFormThrottle,)

    def post(self, request):
        serializer = HappyFormSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        student = request.user.student
        if v["service"] == HappyForm.Service.LIVE_CLASS:
            booking = LiveClassBooking.objects.filter(student=student, reference=v["service_reference"], status__in=[LiveClassBooking.Status.CONFIRMED, LiveClassBooking.Status.COMPLETED], slot__ends_at__lte=timezone.now(), paid_at__isnull=False).select_related("slot", "slot__tutor").first()
            if not booking:
                return Response({"detail": "A completed paid lesson is required."}, status=403)
            title = f"{booking.subject}: {booking.topic}"
            tutor_name = booking.slot.tutor_display_name
        else:
            enrollment = Enrollment.objects.filter(student=student, course__slug=v["service_reference"], status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED]).select_related("course").first()
            if not enrollment or not Payment.objects.filter(student=student, course=enrollment.course, status=Payment.Status.PAID, gateway_verified_at__isnull=False).exists():
                return Response({"detail": "A verified purchased service is required."}, status=403)
            title = enrollment.course.title
            tutor_name = ""
            if v.get("tutor_rating") is not None:
                return Response({"tutor_rating": ["Tutor rating only applies to live classes."]}, status=400)
        try:
            with transaction.atomic():
                form = HappyForm.objects.create(
                    student=student, service=v["service"], service_reference=v["service_reference"],
                    service_title=title, tutor_name=tutor_name, overall_rating=v["overall_rating"],
                    tutor_rating=v.get("tutor_rating"), comments=v.get("comments", ""),
                )
                transaction.on_commit(lambda: deliver_happy_form.delay(str(form.id)))
        except IntegrityError:
            return Response({"detail": "Feedback has already been submitted for this service."}, status=409)
        return Response({"id": str(form.id), "message": "Thank you for your feedback!"}, status=status.HTTP_201_CREATED)
