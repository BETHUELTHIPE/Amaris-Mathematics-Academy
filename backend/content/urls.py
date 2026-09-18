from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .payfast_views import PayFastITNView
from .student_views import (
    CheckoutView,
    PaymentStatusView,
    ProgressView,
    ResumeView,
    StudentCoursesView,
    StudentLessonView,
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
    path("payfast/itn/", PayFastITNView.as_view(), name="payfast-itn"),
    path("student/courses/", StudentCoursesView.as_view(), name="student-courses"),
    path("student/lessons/<slug:course_slug>/<slug:lesson_slug>/", StudentLessonView.as_view(), name="student-lesson"),
    path("student/checkout/", CheckoutView.as_view(), name="student-checkout"),
    path("student/payments/<str:reference>/", PaymentStatusView.as_view(), name="student-payment-status"),
    path("student/progress/", ProgressView.as_view(), name="student-progress"),
    path("student/resume/<slug:course_slug>/", ResumeView.as_view(), name="student-resume"),
    path("bootstrap/", SiteBootstrapView.as_view(), name="site-bootstrap"),
    path("settings/", SiteSettingsView.as_view(), name="site-settings"),
    path("", include(router.urls)),
]
