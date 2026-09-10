from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnnouncementViewSet,
    ContactEnquiryViewSet,
    CourseCategoryViewSet,
    CourseViewSet,
    FAQViewSet,
    NavigationViewSet,
    PageViewSet,
    PricingPlanViewSet,
    SiteBootstrapView,
    SiteSettingsView,
    TestimonialViewSet,
)

router = DefaultRouter()
router.register("navigation", NavigationViewSet, basename="navigation")
router.register("pages", PageViewSet, basename="pages")
router.register("course-categories", CourseCategoryViewSet, basename="course-categories")
router.register("courses", CourseViewSet, basename="courses")
router.register("pricing-plans", PricingPlanViewSet, basename="pricing-plans")
router.register("testimonials", TestimonialViewSet, basename="testimonials")
router.register("faqs", FAQViewSet, basename="faqs")
router.register("announcements", AnnouncementViewSet, basename="announcements")
router.register("enquiries", ContactEnquiryViewSet, basename="enquiries")

urlpatterns = [
    path("bootstrap/", SiteBootstrapView.as_view(), name="site-bootstrap"),
    path("settings/", SiteSettingsView.as_view(), name="site-settings"),
    path("", include(router.urls)),
]
