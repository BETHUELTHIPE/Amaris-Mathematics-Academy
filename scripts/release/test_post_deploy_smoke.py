import json
import unittest
from unittest.mock import patch

from post_deploy_smoke import NoRedirect, get, origin, run

BASE = "https://academy.example.test"
API = "https://api.example.test"
SHA = "a" * 40
HTML = b'<main><h1>Amaris</h1><input name="email"><input name="password"></main>'
HTML += b'<script src="/assets/app.js"></script><link rel="stylesheet" href="/assets/app.css">'


class PostDeploymentSmokeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.responses = {BASE + path: ("text/html", HTML) for path in ("/", "/login", "/courses")}
        self.responses.update(
            {
                API + "/health/": ("application/json", b'{"status":"ok"}'),
                API
                + "/health/ready/": (
                    "application/json",
                    json.dumps(
                        {
                            "status": "ready",
                            "version": {"git_sha": SHA, "image_tag": SHA},
                        }
                    ).encode(),
                ),
                BASE + "/assets/app.js": ("text/javascript", b"console.log('ok');"),
                BASE + "/assets/app.css": ("text/css", b"body { color: black; }"),
            }
        )

    def fetch(self, url):
        self.calls.append(url)
        return self.responses[url]

    def test_all_six_checks_are_explicit_and_bounded(self):
        checks = run(BASE, API, SHA, self.fetch)
        self.assertEqual(len(checks), 6)
        self.assertEqual(len(self.calls), 7)
        self.assertEqual({c["status"] for c in checks}, {"passed"})
        self.assertFalse(any("pay" in url or "register" in url for url in self.calls))

    def test_does_not_fetch_external_or_arbitrary_asset_urls(self):
        bad_assets = b'<script src="https://www.payfast.co.za/eng/process"></script>'
        bad_assets += (
            b'<script src="/api/payments/create.js"></script><script src="/assets/a.js?token=secret"></script>'
        )
        self.responses[BASE + "/"] = ("text/html", HTML + bad_assets)
        run(BASE, API, SHA, self.fetch)
        self.assertEqual(len(self.calls), 7)

    def test_failure_empty_html_bad_health_wrong_version_and_missing_static(self):
        failures = [
            (BASE + "/", ("text/html", b"Service unavailable")),
            (BASE + "/login", ("text/html", b"<main><h1>Login</h1></main>")),
            (API + "/health/", ("text/html", HTML)),
            (API + "/health/ready/", ("application/json", b'{"status":"ready"}')),
            (BASE + "/assets/app.js", ("text/html", HTML)),
            (BASE + "/assets/app.css", ("text/css", b"")),
        ]
        for url, value in failures:
            with self.subTest(url=url), patch.dict(self.responses, {url: value}), self.assertRaises(ValueError):
                run(BASE, API, SHA, self.fetch)

    def test_transport_uses_get_no_auth_no_redirects(self):
        with patch("post_deploy_smoke.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = b"ok"
            get(BASE + "/")
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.method, "GET")
            self.assertIsNone(request.data)
            self.assertNotIn("Authorization", request.headers)
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, 302, None, None, "https://www.payfast.co.za")
        for value in (
            "http://example.test",
            BASE + "/payments",
            BASE + "?token=x",
            "https://u:p@example.test",
        ):
            with self.assertRaises(ValueError):
                origin(value)
