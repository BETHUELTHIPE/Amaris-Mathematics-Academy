"""Authenticated, owner-scoped analytics. No arbitrary person or date-range selectors."""

from django.utils.cache import patch_vary_headers
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .services.analytics import student_analytics, tutor_analytics
from .student_views import StudentAPIView
from .tutor_views import TutorOnlyAPIView


class AnalyticsQuerySerializer(serializers.Serializer):
    days = serializers.ChoiceField(choices=[7, 30, 90], default=30)


class AnalyticsPeriodSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    start = serializers.DateField()
    end = serializers.DateField()
    timezone = serializers.CharField()


class AnalyticsPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    value = serializers.FloatField()


class AnalyticsCategorySerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.FloatField()


class AnalyticsMetricSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    unit = serializers.ChoiceField(choices=["count", "cents", "hours"])
    description = serializers.CharField()
    total = serializers.FloatField()
    series = AnalyticsPointSerializer(many=True)
    breakdown = AnalyticsCategorySerializer(many=True)


class AnalyticsProgressSerializer(serializers.Serializer):
    title = serializers.CharField()
    percent = serializers.FloatField()
    completed = serializers.IntegerField()
    total = serializers.IntegerField()
    description = serializers.CharField()


class AnalyticsResponseSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    role = serializers.ChoiceField(choices=["student", "tutor"])
    period = AnalyticsPeriodSerializer()
    generated_at = serializers.DateTimeField()
    metrics = AnalyticsMetricSerializer(many=True)
    progress = AnalyticsProgressSerializer()


class AnalyticsThrottle(UserRateThrottle):
    scope = "private_analytics"
    rate = "30/min"


class PrivateAnalyticsMixin:
    throttle_classes = (AnalyticsThrottle,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ("Authorization",))
        return response

    def days(self, request):
        if set(request.query_params) - {"days"}:
            raise serializers.ValidationError({"detail": "Only the days filter is supported."})
        query = AnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return query.validated_data["days"]


class StudentAnalyticsView(PrivateAnalyticsMixin, StudentAPIView):
    @extend_schema(parameters=[AnalyticsQuerySerializer], responses=AnalyticsResponseSerializer)
    def get(self, request):
        return Response(student_analytics(self.student, self.days(request)))


class TutorAnalyticsView(PrivateAnalyticsMixin, TutorOnlyAPIView):
    @extend_schema(parameters=[AnalyticsQuerySerializer], responses=AnalyticsResponseSerializer)
    def get(self, request):
        return Response(tutor_analytics(request.user, self.days(request)))
