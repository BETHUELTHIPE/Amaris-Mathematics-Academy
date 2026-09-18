from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .student_views import (
    CheckoutDetailView,
    CheckoutStartView,
    EnrollmentProgressView,
    PayFastITNView,
    PaymentStatusView,
    ProtectedLessonView,
    StudentDashboardView,
)
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
    path("student/dashboard/", StudentDashboardView.as_view(), name="student-dashboard"),
    path("student/checkout/", CheckoutStartView.as_view(), name="student-checkout-start"),
    path("student/checkout/<str:reference>/", CheckoutDetailView.as_view(), name="student-checkout-detail"),
    path("student/payments/<str:reference>/", PaymentStatusView.as_view(), name="student-payment-status"),
    path("student/courses/<slug:course_slug>/progress/", EnrollmentProgressView.as_view(), name="student-progress"),
    path(
        "student/courses/<slug:course_slug>/lessons/<slug:lesson_slug>/",
        ProtectedLessonView.as_view(),
        name="student-lesson",
    ),
    path("payments/payfast/itn/", PayFastITNView.as_view(), name="payfast-itn"),
    path("", include(router.urls)),
]
