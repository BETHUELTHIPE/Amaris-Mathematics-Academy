from django.urls import path
from .views import HappyFormView

urlpatterns = [path("student/feedback/", HappyFormView.as_view(), name="student-happy-form")]
