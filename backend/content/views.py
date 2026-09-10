from django.db.models import Count, Prefetch, Q
from django.utils import timezone
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
    FAQSerializer,
    NavigationItemSerializer,
    PageSerializer,
    PricingPlanSerializer,
    SiteBootstrapSerializer,
    SiteSettingsSerializer,
    TestimonialSerializer,
)


def live_filter(now=None):
    now = now or timezone.now()
    return Q(is_published=True) & (Q(publish_at__isnull=True) | Q(publish_at__lte=now))


class SiteSettingsView(generics.GenericAPIView):
    serializer_class = SiteSettingsSerializer

    def get(self, request):
        settings = SiteSettings.objects.first()
        if settings is None:
            return Response({"detail": "Site settings have not been configured."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(settings).data)


class NavigationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NavigationItemSerializer
    pagination_class = None

    def get_queryset(self):
        return NavigationItem.objects.filter(is_active=True)


class PageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PageSerializer
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self):
        now = timezone.now()
        return Page.objects.filter(live_filter(now)).prefetch_related(
            Prefetch("sections", queryset=PageSection.objects.filter(live_filter(now)).order_by("order"))
        )


class CourseCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseCategorySerializer
    lookup_field = "slug"
    pagination_class = None
    queryset = CourseCategory.objects.filter(is_active=True)


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseSerializer
    lookup_field = "slug"
    filterset_fields = ("category__slug", "curriculum", "academic_level", "featured")
    search_fields = ("title", "short_description", "description", "curriculum", "academic_level")
    ordering_fields = ("title", "price", "order", "created_at")
    ordering = ("order", "title")

    def get_queryset(self):
        now = timezone.now()
        lesson_queryset = Lesson.objects.filter(live_filter(now)).select_related("video").order_by("order")
        module_queryset = CourseModule.objects.filter(is_published=True).prefetch_related(
            Prefetch("lessons", queryset=lesson_queryset)
        )
        return (
            Course.objects.filter(live_filter(now), status=Course.Status.PUBLISHED)
            .select_related("category")
            .prefetch_related(Prefetch("modules", queryset=module_queryset))
            .annotate(
                lesson_count=Count(
                    "modules__lessons",
                    filter=Q(modules__lessons__is_published=True)
                    & (Q(modules__lessons__publish_at__isnull=True) | Q(modules__lessons__publish_at__lte=now)),
                    distinct=True,
                )
            )
        )

    @action(detail=False, methods=["get"])
    def featured(self, request):
        queryset = self.filter_queryset(self.get_queryset().filter(featured=True))
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class PricingPlanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PricingPlanSerializer
    pagination_class = None

    def get_queryset(self):
        return PricingPlan.objects.filter(live_filter()).order_by("order", "price")


class TestimonialViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TestimonialSerializer
    pagination_class = None

    def get_queryset(self):
        return Testimonial.objects.filter(live_filter()).order_by("order")


class FAQViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FAQSerializer
    pagination_class = None
    filterset_fields = ("category",)

    def get_queryset(self):
        return FAQ.objects.filter(live_filter()).order_by("order")


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
