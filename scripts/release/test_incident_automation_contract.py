from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "incident" / "validate_incident.py"
SPEC = importlib.util.spec_from_file_location("validate_incident", VALIDATOR_PATH)
assert SPEC and SPEC.loader
validate_incident = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_incident)


class IncidentAutomationContractTests(unittest.TestCase):
    def test_sanitizer_discards_untrusted_fields_and_query_strings(self):
        raw = {
            "source": "django",
            "environment": "production",
            "severity": "critical",
            "release_sha": "a" * 40,
            "authorization": "Bearer should-never-survive",
            "event": {
                "status_code": 500,
                "method": "GET",
                "path": "/checkout/?email=student@example.test&token=secret",
                "exception_type": "ValueError",
                "message": "student@example.test",
                "frames": [
                    {
                        "file": "/srv/app/backend/content/views.py",
                        "line": 42,
                        "function": "checkout",
                        "source": "secret = request.headers['Authorization']",
                    }
                ],
            },
        }

        sanitized = validate_incident.sanitize_incident(raw)
        rendered = json.dumps(sanitized)

        self.assertEqual(sanitized["event"]["path"], "/checkout/")
        self.assertNotIn("student@example.test", rendered)
        self.assertNotIn("Bearer", rendered)
        self.assertNotIn("Authorization", rendered)
        self.assertNotIn("message", sanitized["event"])
        self.assertNotIn("source", sanitized["event"]["frames"][0])

    def test_monitor_dispatches_only_sanitized_repository_event(self):
        workflow = (
            ROOT / ".github" / "workflows" / "production-monitor.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "*/5 * * * *"', workflow)
        self.assertIn("validate_incident.py", workflow)
        self.assertIn('"production_incident"', workflow)
        self.assertIn("PRODUCTION_HEALTHCHECK_URL", workflow)
        self.assertNotIn("PRODUCTION_DEPLOY_TOKEN", workflow)

    def test_incident_response_never_auto_merges_or_deploys_code_fix(self):
        workflow = (
            ROOT / ".github" / "workflows" / "incident-response.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("rollback-target production", workflow)
        self.assertIn("PRODUCTION_AUTO_ROLLBACK", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("INCIDENT_BOT_TOKEN", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertNotIn("deploy production", workflow)

    def test_incident_email_uses_company_letterhead(self):
        template = (
            ROOT
            / "scripts"
            / "incident"
            / "templates"
            / "production_incident.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-company-letterhead="true"', template)
        self.assertIn("$company_name", template)
        self.assertIn("$company_logo_url", template)
        self.assertIn("$company_address", template)

    def test_sanitized_payload_can_be_written_as_json(self):
        payload = validate_incident.sanitize_incident(None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incident.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(json.loads(path.read_text())["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
