"""Student video requests, authenticated with Supabase; tutor totals use Django sessions elsewhere."""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from content.authentication import SupabaseStudentAuthentication
from content.services.payments import PaymentSecurityError
from content.services.topical_videos import create_video_checkout, video_price
from content.tutor_finance_models import TutorContract, TutorVideoRequest


class VideoRequestSerializer(serializers.Serializer):
    tutor_id = serializers.IntegerField(min_value=1)
    programme = serializers.CharField(max_length=60)
    topic = serializers.CharField(max_length=180)
    idempotency_key = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class VideoCheckoutResponseSerializer(serializers.Serializer):
    reference = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    gateway_url = serializers.URLField()
    fields = serializers.DictField(child=serializers.CharField())


class VideoOrderStatusSerializer(serializers.Serializer):
    reference = serializers.CharField()
    status = serializers.CharField()
    topic = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class TutorVideoOptionsView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: serializers.DictField()})
    def get(self, request):
        ids = (
            TutorContract.objects.filter(
                service=TutorContract.Service.VIDEO,
                is_active=True,
                effective_from__lte=timezone.now(),
            )
            .filter(Q(effective_until__isnull=True) | Q(effective_until__gt=timezone.now()))
            .values_list("tutor_id", flat=True)
            .distinct()
        )
        tutors = (
            get_user_model()
            .objects.filter(pk__in=ids, is_active=True, is_staff=False)
            .order_by("first_name", "last_name")
        )
        return Response(
            {
                "price": str(video_price()),
                "currency": "ZAR",
                "tutors": [
                    {"id": tutor.pk, "name": tutor.get_full_name().strip() or tutor.get_username()} for tutor in tutors
                ],
            }
        )


class VideoRequestCheckoutView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=VideoRequestSerializer, responses={201: VideoCheckoutResponseSerializer})
    def post(self, request):
        data = VideoRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        tutor = (
            get_user_model().objects.filter(pk=data.validated_data["tutor_id"], is_active=True, is_staff=False).first()
        )
        if tutor is None:
            return Response({"detail": "Tutor is not available."}, status=status.HTTP_404_NOT_FOUND)
        try:
            checkout = create_video_checkout(
                student=request.user.student,
                tutor=tutor,
                programme=data.validated_data["programme"],
                topic=data.validated_data["topic"],
                idempotency_key=data.validated_data["idempotency_key"],
            )
        except PaymentSecurityError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        order = TutorVideoRequest.objects.get(reference=checkout.payment_reference)
        return Response(
            {
                "reference": order.reference,
                "status": order.status,
                "amount": order.price,
                "gateway_url": checkout.gateway_url,
                "fields": checkout.fields,
            },
            status=status.HTTP_201_CREATED,
        )


class VideoRequestStatusView(APIView):
    authentication_classes = (SupabaseStudentAuthentication,)
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: VideoOrderStatusSerializer})
    def get(self, request, reference):
        order = TutorVideoRequest.objects.filter(student=request.user.student, reference=reference).first()
        if not order:
            return Response({"detail": "Video request not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "reference": order.reference,
                "status": order.status,
                "topic": order.topic,
                "amount": order.price,
            }
        )
