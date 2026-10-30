from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


class AcademyWorkspaceTests(TestCase):
    def test_course_editor_only_receives_authorized_tools(self):
        editor = get_user_model().objects.create_user("course-editor", is_staff=True)
        editor.user_permissions.add(Permission.objects.get(codename="view_course", content_type__app_label="content"))
        self.client.force_login(editor)
        response = self.client.get(reverse("admin:index"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/admin/content/course/"')
        self.assertNotContains(response, 'href="/admin/content/payment/"')
        self.assertNotContains(response, 'href="/admin/content/course/add/"')
        self.assertNotContains(response, "/admin/monitoring/")
        self.assertContains(response, "Learning &amp; courses")

    def test_superuser_receives_existing_monitoring_links(self):
        user = get_user_model().objects.create_superuser("workspace-admin", "qa@example.invalid", "synthetic-test-only")
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"), secure=True)
        self.assertContains(response, 'href="/admin/monitoring/grafana/"')
        self.assertContains(response, 'href="/admin/content/liveclassbooking/"')
        self.assertContains(response, "Recently updated")

    def test_login_has_explicit_labels_and_standard_csrf_protection(self):
        response = self.client.get(reverse("admin:login"), secure=True)
        self.assertContains(response, 'for="id_username"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "admin/amaris-admin.")
