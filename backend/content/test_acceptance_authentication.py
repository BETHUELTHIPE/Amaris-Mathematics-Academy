from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory, APITestCase

from content.authentication import SupabaseStudentAuthentication
from content.models import StudentRecord


@override_settings(
    ACCEPTANCE_GITHUB_OIDC_ENABLED=True,
    ACCEPTANCE_GITHUB_AUDIENCE="amaris-staging",
    ACCEPTANCE_GITHUB_REPOSITORY="BETHUELTHIPE/Amaris-Mathematics-Academy",
    ACCEPTANCE_GITHUB_ENVIRONMENT="staging",
    ACCEPTANCE_GITHUB_REF="refs/heads/main",
)
class AcceptanceAuthenticationTests(APITestCase):
    claims = {
        "repository": "BETHUELTHIPE/Amaris-Mathematics-Academy",
        "event_name": "push",
        "environment": "staging",
        "ref": "refs/heads/main",
        "run_id": "12345",
        "sha": "a" * 40,
        "exp": 4_102_444_800,
        "iat": 1_700_000_000,
        "nbf": 1_700_000_000,
    }

    def authenticate_acceptance_user(self, label: str):
        request = APIRequestFactory().get(
            "/",
            HTTP_X_AMARIS_ACCEPTANCE_USER=label,
        )
        authenticator = SupabaseStudentAuthentication()
        with (
            patch.object(
                authenticator,
                "_authenticate_github_acceptance",
                wraps=authenticator._authenticate_github_acceptance,
            ),
            patch(
                "content.authentication._GITHUB_JWK_CLIENT.get_signing_key_from_jwt",
                return_value=SimpleNamespace(key="test-key"),
            ),
            patch(
                "content.authentication.decode_jwt",
                return_value=self.claims,
            ),
        ):
            return authenticator._authenticate_github_acceptance(
                "synthetic-token",
                request=request,
            )

    def test_distinct_capacity_users_receive_distinct_stable_students(self):
        first, first_auth = self.authenticate_acceptance_user("capacity-100-1")
        second, second_auth = self.authenticate_acceptance_user("capacity-100-2")
        repeated, repeated_auth = self.authenticate_acceptance_user("capacity-100-1")

        self.assertNotEqual(first.student.pk, second.student.pk)
        self.assertEqual(first.student.pk, repeated.student.pk)
        self.assertEqual(first_auth["acceptance_user"], "capacity-100-1")
        self.assertEqual(second_auth["acceptance_user"], "capacity-100-2")
        self.assertEqual(repeated_auth["acceptance_user"], "capacity-100-1")
        self.assertEqual(StudentRecord.objects.count(), 2)

    def test_invalid_capacity_user_identifier_is_rejected(self):
        with self.assertRaisesRegex(
            AuthenticationFailed,
            "synthetic acceptance user identifier is invalid",
        ):
            self.authenticate_acceptance_user("capacity user with spaces")
