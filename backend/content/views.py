from django.conf import settings
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import (
    FAQ,
    Announcement,
    ContactEnquiry,
    Course,
    CourseCategory,
    CourseModule,
    Lesson,
    NavigationItem,
    Page,
    PageSection,
    PricingPlan,
    SiteSettings,
    Testimonial,
)
from .serializers import (
    AnnouncementSerializer,
    ContactEnquirySerializer,
    CourseCategorySerializer,
    CourseSerializer,
    CourseSummarySerializer,
    FAQSerializer,
    NavigationItemSerializer,
    PageSerializer,
    PricingPlanSerializer,
    SiteBootstrapSerializer,
    SiteSettingsSerializer,
    TestimonialSerializer,
)


def public_cache(seconds: int):
    return method_decorator(cache_page(seconds, cache="public_content", key_prefix="public-api-v1"), name="dispatch")


def live_filter(now=None):
    now = now or timezone.now()
    return Q(is_published=True) & (Q(publish_at__isnull=True) | Q(publish_at__lte=now))


@public_cache(settings.PUBLIC_CONTENT_CACHE_SECONDS)
class SiteSettingsView(generics.GenericAPIView):
    serializer_class = SiteSettingsSerializer

    def get(self, request):
        settings = SiteSettings.objects.first()
        if settings is None:
            return Response({"detail": "Site settings have not been configured."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(settings).data)


@public_cache(settings.PUBLIC_CONTENT_CACHE_SECONDS)
class NavigationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NavigationItemSerializer
    pagination_class = None

    def get_queryset(self):
        return NavigationItem.objects.filter(is_active=True)


@public_cache(settings.PUBLIC_CONTENT_CACHE_SECONDS)
class PageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PageSerializer
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self):
        now = timezone.now()
        return Page.objects.filter(live_filter(now)).prefetch_related(
            Prefetch("sections", queryset=PageSection.objects.filter(live_filter(now)).order_by("order"))
        )


@public_cache(settings.PUBLIC_CONTENT_CACHE_SECONDS)
class CourseCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseCategorySerializer
    lookup_field = "slug"
    pagination_class = None
    queryset = CourseCategory.objects.filter(is_active=True)


@public_cache(settings.PUBLIC_CONTENT_CACHE_SECONDS)
class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseSerializer
    lookup_field = "slug"
    filterset_fields = ("category__slug", "curriculum", "academic_level", "featured")
    search_fields = ("title", "short_description", "description", "curriculum", "academic_level")
    ordering_fields = ("title", "price", "order", "created_at")
    ordering = ("order", "title")

    def get_serializer_class(self):
        if getattr(self, "action", None) in {"list", "featured"}:
            return CourseSummarySerializer
        return CourseSerializer

    def get_queryset(self):
        now = timezone.now()
        lesson_queryset = Lesson.objects.filter(live_filter(now)).order_by("order")
        module_queryset = CourseModule.objects.filter(is_published=True).prefetch_related(
            Prefetch("lessons", queryset=lesson_queryset)
        )
        queryset = (
            Course.objects.filter(live_filter(now), status=Course.Status.PUBLISHED)
            .select_related("category")
            .annotate(
                lesson_count=Count(
                    "modules__lessons",
                    filter=Q(modules__lessons__is_published=True)
                    & (Q(modules__lessons__publish_at__isnull=True) | Q(modules__lessons__publish_at__lte=now)),
                    distinct=True,
                )
            )
        )
        if getattr(self, "action", None) in {"list", "featured"}:
            queryset = queryset.defer("description", "outcomes")
        if getattr(self, "action", None) == "retrieve":
            queryset = queryset.prefetch_related(Prefetch("modules", queryset=module_queryset))
        return queryset

    @action(detail=False, methods=["get"])
    def featured(self, request):
        queryset = self.filter_queryset(self.get_queryset().filter(featured=True))
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


@public_cache(settings.PUBLIC_CONTENT_CACHE_SECONDS)
class PricingPlanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PricingPlanSerializer
    pagination_class = None

    def get_queryset(self):
        return PricingPlan.objects.filter(live_filter()).order_by("order", "price")


@public_cache(settings.PUBLIC_CONTENT_CACHE_SECONDS)
class TestimonialViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TestimonialSerializer
    pagination_class = None

    def get_queryset(self):
        return Testimonial.objects.filter(live_filter()).order_by("order")


@public_cache(settings.PUBLIC_CONTENT_CACHE_SECONDS)
class FAQViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FAQSerializer
    pagination_class = None
    filterset_fields = ("category",)

    def get_queryset(self):
        return FAQ.objects.filter(live_filter()).order_by("order")


@public_cache(settings.SITE_BOOTSTRAP_CACHE_SECONDS)
class AnnouncementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AnnouncementSerializer
    pagination_class = None

    def get_queryset(self):
        now = timezone.now()
        return Announcement.objects.filter(live_filter(now)).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))


class EnquiryThrottle(AnonRateThrottle):
    scope = "enquiries"


class ContactEnquiryViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = ContactEnquiry.objects.none()
    serializer_class = ContactEnquirySerializer
    throttle_classes = (EnquiryThrottle,)


class AssistantThrottle(AnonRateThrottle):
    scope = "assistant"


class AmarisAssistantView(APIView):
    throttle_classes = (AssistantThrottle,)

    def post(self, request):
        message = request.data.get("message")
        if not isinstance(message, str) or not message.strip():
            return Response({"detail": "Enter a question for Amaris Assistant."}, status=status.HTTP_400_BAD_REQUEST)
        if len(message) > 1200:
            return Response(
                {"detail": "Keep your question under 1,200 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not getattr(settings, "OPENAI_API_KEY", ""):
            return Response(
                {"detail": "Amaris Assistant is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            answer, _response_id = answer_website_question(message)
        except (RuntimeError, ValueError):
            return Response(
                {"detail": "Amaris Assistant is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"answer": answer}, status=status.HTTP_200_OK)


@public_cache(settings.SITE_BOOTSTRAP_CACHE_SECONDS)
class SiteBootstrapView(generics.GenericAPIView):
    """One request for global website content used by the public frontend shell."""

    serializer_class = SiteBootstrapSerializer

    def get(self, request):
        now = timezone.now()
        settings = SiteSettings.objects.first()
        announcements = Announcement.objects.filter(live_filter(now)).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
        payload = {
            "settings": SiteSettingsSerializer(settings, context={"request": request}).data if settings else None,
            "navigation": NavigationItemSerializer(
                NavigationItem.objects.filter(is_active=True), many=True, context={"request": request}
            ).data,
            "announcements": AnnouncementSerializer(announcements, many=True, context={"request": request}).data,
        }
        return Response(payload)
