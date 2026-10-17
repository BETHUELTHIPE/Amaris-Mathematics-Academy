"""Regression tests for Django Admin list performance and permissions."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from .models import (
    ContactEnquiry,
    Course,
    CourseCategory,
    CourseModule,
    Lesson,
    SiteSettings,
)


class AdminPerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = get_user_model().objects.create_superuser(
            username="admin-performance",
            email="admin-performance@example.com",
            password="Strong-Test-Password-123!",
        )
        cls.category = CourseCategory.objects.create(name="CAPS", slug="caps")

    def changelist(self, model):
        model_admin = admin.site._registry[model]
        request = RequestFactory().get(f"/admin/content/{model._meta.model_name}/")
        request.user = self.superuser
        return model_admin.get_changelist_instance(request)

    def create_course(self, number):
        return Course.objects.create(
            category=self.category,
            title=f"Mathematics {number}",
            slug=f"mathematics-{number}",
            short_description="Mathematics tutoring",
            description="CAPS course",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
        )

    def test_course_changelist_does_not_query_category_per_row(self):
        for number in range(12):
            self.create_course(number)

        changelist = self.changelist(Course)
        with self.assertNumQueries(1):
            labels = [(course.title, course.category.name) for course in changelist.result_list]

        self.assertEqual(len(labels), 12)
        self.assertTrue(all(category == "CAPS" for _, category in labels))

    def test_lesson_changelist_preloads_nested_course(self):
        course = self.create_course(50)
        module = CourseModule.objects.create(course=course, title="Calculus", order=1)
        for number in range(12):
            Lesson.objects.create(
                module=module,
                title=f"Derivatives {number}",
                slug=f"derivatives-{number}",
                order=number,
            )

        changelist = self.changelist(Lesson)
        with self.assertNumQueries(1):
            labels = [
                (lesson.module.title, lesson.module.course.title)
                for lesson in changelist.result_list
            ]

        self.assertEqual(len(labels), 12)
        self.assertTrue(all(title == course.title for _, title in labels))

    def test_enquiry_changelist_preloads_assigned_staff(self):
        for number in range(12):
            ContactEnquiry.objects.create(
                name=f"Student {number}",
                email=f"student{number}@example.com",
                subject="Classes",
                message="Please provide the timetable.",
                assigned_to=self.superuser,
            )

        changelist = self.changelist(ContactEnquiry)
        with self.assertNumQueries(1):
            usernames = [
                enquiry.assigned_to.username for enquiry in changelist.result_list
            ]

        self.assertEqual(usernames, [self.superuser.username] * 12)

    def test_large_changelists_do_not_run_redundant_full_count(self):
        for model in (Course, Lesson, ContactEnquiry):
            self.assertFalse(admin.site._registry[model].show_full_result_count)

    def test_site_settings_add_permission_respects_django_permissions(self):
        settings_admin = admin.site._registry[SiteSettings]
        request = RequestFactory().get("/admin/content/sitesettings/add/")
        request.user = get_user_model().objects.create_user(
            username="limited-staff", is_staff=True
        )
        self.assertFalse(settings_admin.has_add_permission(request))

        request.user = self.superuser
        self.assertTrue(settings_admin.has_add_permission(request))
        SiteSettings.objects.create()
        self.assertFalse(settings_admin.has_add_permission(request))
