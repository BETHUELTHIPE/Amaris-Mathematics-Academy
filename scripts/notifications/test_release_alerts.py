"""Offline contract tests for protected Amaris notification workflows."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("release_alerts.py")
spec = importlib.util.spec_from_file_location("release_alerts", MODULE_PATH)
alerts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alerts)


class NotificationTests(unittest.TestCase):
    def test_lighthouse_failure_and_success_are_reported_separately(self):
        event = {"workflow_run": {
            "id": 42, "name": "Browser LCP CLS and Mobile Responsiveness",
            "head_branch": "perf/test", "head_sha": "abc123456789",
            "conclusion": "failure", "status": "completed",
            "html_url": "https://github.com/example/actions/runs/42",
        }}
        calls = []

        def failed_jobs(url, token):
            calls.append((url, token))
            return {"jobs": [{"name": "browser-performance",
                              "steps": [{"name": "Run existing strict mobile Lighthouse",
                                         "conclusion": "failure"}]}]}

        subject, body = alerts.lighthouse_summary(event, "token-not-logged", fetch=failed_jobs)
        self.assertIn("FAILED", subject)
        self.assertIn("Overall CI workflow: FAILURE", body)
        self.assertIn("actions/runs/42", body)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("token-not-logged", body)

        def passed_jobs(_url, _token):
            return {"jobs": [{"name": "browser-performance", "steps": [
                {"name": "Run existing strict mobile Lighthouse", "conclusion": "success"}]}]}

        subject, body = alerts.lighthouse_summary(event, "ignored", fetch=passed_jobs)
        self.assertIn("PASSED", subject)
        self.assertIn("Step results:", body)
        self.assertIn("Overall CI workflow: FAILURE", body)

        def not_run_jobs(_url, _token):
            return {"jobs": [{"name": "frontend", "steps": [
                {"name": "Install dependencies", "conclusion": "failure"},
                {"name": "Lighthouse CI", "conclusion": "skipped"}]}]}

        subject, body = alerts.lighthouse_summary(event, "ignored", fetch=not_run_jobs)
        self.assertIn("NOT RUN", subject)
        self.assertIn("skipped", body)

    def test_render_notifications_initialize_without_history_and_no_duplicates(self):
        a, b = list(alerts.SERVICES)[:2]
        first_deploys = {
            a: [{"id": "dep-old", "status": "live", "commit": {"id": "a" * 40}}],
            b: [{"id": "dep-prev", "status": "deactivated", "commit": {"id": "b" * 40}}],
        }
        results = dict(first_deploys)
        sent = []

        def fetch(url, _token):
            service = url.split("/services/")[1].split("/")[0]
            return [{"deploy": obj, "cursor": "unused"} for obj in results.get(service, [])]

        def send(subject, body, dry_run=False):
            sent.append((subject, body))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alerts.json"
            alerts.poll_render(path, "token", fetch=fetch, send=send)
            self.assertTrue(path.exists())
            self.assertEqual(sent, [])
            results[a] = first_deploys[a] + [
                {"id": "dep-new-pass", "status": "live",
                 "finishedAt": "2026-10-19T17:10:00Z", "commit": {"id": "c" * 40}},
                {"id": "dep-new-fail", "status": "build_failed",
                 "finishedAt": "2026-10-19T17:15:00Z", "commit": {"id": "d" * 40}},
            ]
            alerts.poll_render(path, "token", fetch=fetch, send=send)
            self.assertEqual(len(sent), 2)
            self.assertIn("PASSED", sent[0][0])
            self.assertIn("FAILED", sent[1][0])
            alerts.poll_render(path, "token", fetch=fetch, send=send)
            self.assertEqual(len(sent), 2)

    def test_does_not_mark_unsent_deploy_as_notified(self):
        service = list(alerts.SERVICES)[0]
        state = {"seen": {service: ["dep-old"]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alerts.json"
            path.write_text(json.dumps(state))

            def fetch(url, _token):
                if service in url:
                    return [{"deploy": {"id": "dep-new", "status": "build_failed"}}]
                return []

            def bad_send(_subject, _body, dry_run=False):
                raise RuntimeError("SMTP rejected")

            with self.assertRaisesRegex(RuntimeError, "SMTP rejected"):
                alerts.poll_render(path, "token", fetch=fetch, send=bad_send)
            self.assertEqual(json.loads(path.read_text()), state)

    def test_render_failure_never_claims_success(self):
        sid = next(iter(alerts.SERVICES))
        subject, body = alerts.render_deployment_summary(
            sid, {"id": "dep-test", "status": "pre_deploy_failed",
                  "commit": {"id": "deadbeef"}, "finishedAt": "2026-10-19T17:00:00Z"}
        )
        self.assertIn("FAILED", subject)
        self.assertIn("pre_deploy_failed", body)

    def test_email_header_safety_and_recipients(self):
        self.assertEqual(alerts.recipients("person@example.com, other@example.org"),
                         ["person@example.com", "other@example.org"])
        self.assertEqual(alerts.clean("unsafe\r\n Bcc: injected"), "unsafe Bcc: injected")


if __name__ == "__main__":
    unittest.main()
