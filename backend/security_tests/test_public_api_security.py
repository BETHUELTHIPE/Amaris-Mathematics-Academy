from django.test import TestCase
from rest_framework.test import APIClient


class PublicApiSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_sql_injection_payload_does_not_expose_database_errors(self):
        response = self.client.get("/api/v1/courses/", {"search": "' OR 1=1 --"})
        body = response.content.decode("utf-8", errors="ignore").lower()
        self.assertNotIn("syntax error", body)
        self.assertNotIn("traceback", body)
        self.assertNotIn("django.db", body)

    def test_xss_payload_is_not_reflected_from_search(self):
        payload = "<script>alert(1)</script>"
        response = self.client.get("/api/v1/courses/", {"search": payload})
        body = response.content.decode("utf-8", errors="ignore")
        self.assertNotIn(payload, body)

    def test_path_traversal_style_slug_does_not_leak_filesystem(self):
        response = self.client.get("/api/v1/pages/../../etc/passwd/")
        body = response.content.decode("utf-8", errors="ignore").lower()
        self.assertNotIn("/etc/passwd", body)
        self.assertNotIn("root:x:", body)

    def test_error_responses_do_not_leak_stack_traces(self):
        response = self.client.get("/api/v1/definitely-not-a-real-endpoint/")
        body = response.content.decode("utf-8", errors="ignore").lower()
        self.assertNotIn("traceback", body)
        self.assertNotIn("secret_key", body)
        self.assertNotIn("database_url", body)
