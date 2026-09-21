from __future__ import annotations

import hashlib
import json
import time
import uuid
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import jwt
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from .authentication import AuthenticationServiceUnavailable, SupabaseStudentAuthentication
from .models import StudentRecord


@override_settings(
    SUPABASE_URL="https://auth.example.test",
    SUPABASE_PUBLISHABLE_KEY="synthetic-publishable-key",
    SUPABASE_AUTH_CACHE_SECONDS=15,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class StudentAuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.auth = SupabaseStudentAuthentication()
        self.factory = APIRequestFactory()
        self.user_id = str(uuid.UUID("00000000-0000-4000-8000-000000000123"))
        self.payload = {
            "id": self.user_id,
            "email": "student@example.test",
            "email_confirmed_at": "2026-09-21T00:00:00Z",
            "user_metadata": {"first_name": "Synthetic", "last_name": "Student"},
        }
        self.token = self.make_token()

    def make_token(self, **claims):
        return jwt.encode(
            {"exp": int(time.time()) + 300, **claims}, "synthetic-test-signing-key-only-123456", algorithm="HS256"
        )

    def request(self, token=None, **headers):
        return self.factory.get(
            "/api/v1/student/courses/", HTTP_AUTHORIZATION=f"Bearer {token or self.token}", **headers
        )

    def upstream(self, payload=None):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            self.payload if payload is None else payload
        ).encode()
        return patch("content.authentication.urlopen", return_value=response)

    def test_missing_authorization_is_anonymous(self):
        self.assertIsNone(self.auth.authenticate(self.factory.get("/")))

    def test_malformed_authorization_is_rejected(self):
        for header in ["Basic abc", "Bearer", "Bearer one two"]:
            with self.subTest(header=header), self.assertRaises(AuthenticationFailed):
                self.auth.authenticate(self.factory.get("/", HTTP_AUTHORIZATION=header))

    def test_confirmed_user_is_validated_by_auth_and_linked_by_id(self):
        with self.upstream() as upstream:
            principal, details = self.auth.authenticate(self.request())
        self.assertEqual(principal.supabase_user_id, self.user_id)
        self.assertEqual(principal.email, self.payload["email"])
        self.assertTrue(principal.is_authenticated)
        self.assertEqual(details["provider"], "supabase")
        request = upstream.call_args.args[0]
        self.assertEqual(request.full_url, "https://auth.example.test/auth/v1/user")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.token}")
        self.assertEqual(StudentRecord.objects.count(), 1)

    def test_unconfirmed_email_cannot_be_forged_in_metadata(self):
        self.payload["email_confirmed_at"] = None
        self.payload["user_metadata"]["email_verified"] = True
        with self.upstream(), self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self.request())
        self.assertFalse(StudentRecord.objects.exists())

    def test_incomplete_user_is_rejected(self):
        for field in ["id", "email"]:
            payload = {**self.payload, field: ""}
            with self.subTest(field=field), self.upstream(payload), self.assertRaises(AuthenticationFailed):
                cache.clear()
                self.auth.authenticate(self.request())

    def test_inactive_student_is_rejected(self):
        StudentRecord.objects.create(supabase_user_id=self.user_id, email=self.payload["email"], is_active=False)
        with self.upstream(), self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self.request())

    def test_email_collision_never_links_to_another_student(self):
        StudentRecord.objects.create(supabase_user_id=uuid.uuid4(), email=self.payload["email"])
        with self.upstream(), self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self.request())
        self.assertEqual(StudentRecord.objects.count(), 1)

    def test_invalid_or_expired_token_cannot_use_cached_user(self):
        for token in [
            "malformed",
            self.make_token(exp=int(time.time()) - 1),
            jwt.encode({}, "synthetic-test-signing-key-only-123456", algorithm="HS256"),
        ]:
            digest = hashlib.sha256(token.encode()).hexdigest()
            cache.set(f"supabase-auth:{digest}", self.payload)
            with (
                self.subTest(token_type=token[:8]),
                patch("content.authentication.urlopen") as upstream,
                self.assertRaises(AuthenticationFailed),
            ):
                self.auth.authenticate(self.request(token))
            upstream.assert_not_called()

    def test_forged_unexpired_token_still_requires_auth_server_validation(self):
        with (
            patch(
                "content.authentication.urlopen",
                side_effect=HTTPError("https://auth.example.test", 401, "Invalid JWT", {}, None),
            ),
            self.assertRaises(AuthenticationFailed),
        ):
            self.auth.authenticate(self.request())

    def test_cache_lifetime_never_exceeds_token_lifetime(self):
        now = int(time.time())
        token = self.make_token(exp=now + 3)
        with (
            self.upstream(),
            patch("content.authentication.time.time", return_value=now),
            patch("content.authentication.cache.set") as setter,
        ):
            self.auth.authenticate(self.request(token))
        self.assertEqual(setter.call_args.kwargs["timeout"], 3)
        self.assertNotIn(token, setter.call_args.args[0])

    def test_validated_tokens_are_cached_by_digest(self):
        with self.upstream() as upstream:
            self.auth.authenticate(self.request())
            self.auth.authenticate(self.request())
        self.assertEqual(upstream.call_count, 1)

    def test_cache_outage_still_validates_upstream(self):
        with (
            self.upstream() as upstream,
            patch("content.authentication.cache.get", side_effect=OSError),
            patch("content.authentication.cache.set", side_effect=OSError),
        ):
            principal, _ = self.auth.authenticate(self.request())
        self.assertEqual(principal.supabase_user_id, self.user_id)
        upstream.assert_called_once()

    def test_auth_service_outage_fails_closed(self):
        for error in [
            URLError("unavailable"),
            TimeoutError(),
            HTTPError("https://auth.example.test", 503, "Unavailable", {}, None),
        ]:
            with (
                self.subTest(error=type(error).__name__),
                patch("content.authentication.urlopen", side_effect=error),
                self.assertRaises(AuthenticationServiceUnavailable),
            ):
                self.auth.authenticate(self.request())

    def test_non_object_auth_response_is_a_service_error(self):
        with self.upstream([]), self.assertRaises(AuthenticationServiceUnavailable):
            self.auth.authenticate(self.request())

    @override_settings(ACCEPTANCE_GITHUB_OIDC_ENABLED=False)
    def test_synthetic_auth_header_cannot_bypass_disabled_acceptance(self):
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self.request(HTTP_X_AMARIS_ACCEPTANCE="github-actions"))
