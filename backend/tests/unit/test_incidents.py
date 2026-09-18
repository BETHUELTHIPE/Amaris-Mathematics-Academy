import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from amaris_cms.incidents import (
    IncidentDispatchError,
    build_incident,
    dispatch_incident_to_github,
)


class ProductionIncidentTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _raise_example(self):
        def inner():
            raise ValueError("student@example.test bearer super-secret-value")

        try:
            inner()
        except ValueError as exc:
            return exc
        raise AssertionError("unreachable")

    def test_incident_does_not_collect_query_headers_body_or_exception_message(self):
        request = self.factory.get(
            "/api/v1/courses/?email=student@example.test&token=super-secret-value",
            HTTP_AUTHORIZATION="Bearer super-secret-value",
            HTTP_COOKIE="sessionid=super-secret-value",
        )
        request.correlation_reference = "AMR-12345678ABCDEF"
        request.resolver_match = SimpleNamespace(route="api/v1/courses/")

        incident = build_incident(request, self._raise_example())
        rendered = json.dumps(incident)

        self.assertEqual(incident["event"]["path"], "api/v1/courses/")
        self.assertEqual(
            incident["event"]["correlation_reference"],
            "AMR-12345678ABCDEF",
        )
        self.assertNotIn("student@example.test", rendered)
        self.assertNotIn("super-secret-value", rendered)
        self.assertNotIn("Authorization", rendered)
        self.assertNotIn("Cookie", rendered)
        self.assertNotIn("sessionid", rendered)
        self.assertNotIn("ValueError(", rendered)
        self.assertTrue(incident["event"]["frames"])

    def test_invalid_release_sha_is_not_reported_as_release_identity(self):
        request = self.factory.get("/health/")
        exc = self._raise_example()
        with patch.dict(
            os.environ,
            {"RELEASE_SHA": "latest", "APP_ENVIRONMENT": "production"},
            clear=False,
        ):
            incident = build_incident(request, exc)

        self.assertEqual(incident["release_sha"], "unknown")
        self.assertEqual(incident["environment"], "production")

    @patch("amaris_cms.incidents.url_request.urlopen")
    def test_repository_dispatch_uses_only_configured_token(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.status = 204
        urlopen.return_value = response
        incident = {
            "schema_version": 1,
            "source": "django",
            "environment": "production",
            "severity": "error",
            "fingerprint": "a" * 24,
            "release_sha": "b" * 40,
            "occurred_at": "2026-09-18T00:00:00+00:00",
            "event": {},
        }

        with patch.dict(
            os.environ,
            {
                "INCIDENT_GITHUB_TOKEN": "test-token-not-real",
                "INCIDENT_GITHUB_REPOSITORY": (
                    "BETHUELTHIPE/Amaris-Mathematics-Academy"
                ),
            },
            clear=False,
        ):
            dispatch_incident_to_github(incident)

        outgoing = urlopen.call_args.args[0]
        body = json.loads(outgoing.data.decode("utf-8"))
        self.assertEqual(body["event_type"], "production_incident")
        self.assertEqual(body["client_payload"], incident)
        self.assertEqual(
            outgoing.headers["Authorization"],
            "Bearer test-token-not-real",
        )

    def test_missing_dispatch_token_fails_closed(self):
        with patch.dict(os.environ, {"INCIDENT_GITHUB_TOKEN": ""}, clear=False):
            with self.assertRaises(IncidentDispatchError):
                dispatch_incident_to_github({"fingerprint": "a" * 24})
