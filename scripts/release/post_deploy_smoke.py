"""Bounded, read-only production probes. No credentials, redirects or payments."""

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 5_000_000


def origin(value):
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
    ):
        raise ValueError("Smoke origins must be HTTPS roots without credentials, query or fragment")
    return f"https://{parts.netloc}"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Smoke requests must not follow redirects")


def get(url):
    request = Request(url, method="GET", headers={"Accept": "*/*", "Cache-Control": "no-cache"})
    with build_opener(NoRedirect).open(request, timeout=10) as response:
        body = response.read(MAX_BYTES + 1)
        if response.status != 200 or not body or len(body) > MAX_BYTES:
            raise ValueError("Smoke response status or size failed")
        return response.headers.get_content_type(), body


class Page(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.main = False
        self.heading = False
        self.inputs = set()
        self.assets = []
        self.feed(body.decode("utf-8"))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.main |= tag == "main"
        self.heading |= tag == "h1"
        if tag == "input":
            self.inputs.add(attrs.get("name"))
        if tag == "script" and attrs.get("src"):
            self.assets.append(("script", attrs["src"]))
        if tag == "link" and "stylesheet" in (attrs.get("rel") or "").split() and attrs.get("href"):
            self.assets.append(("style", attrs["href"]))


def run(base_url, api_url, expected_sha, fetch=get):
    base, api = origin(base_url), origin(api_url)
    checks = []

    def passed(name):
        checks.append({"name": name, "status": "passed"})

    def html(path, name):
        content_type, body = fetch(base + path)
        if content_type != "text/html":
            raise ValueError("Expected HTML")
        page = Page(body)
        if not page.main or not page.heading:
            raise ValueError("Expected application content")
        passed(name)
        return page

    home = html("/", "homepage")
    login = html("/login", "login-page")
    if not {"email", "password"} <= login.inputs:
        raise ValueError("Login form unavailable")
    html("/courses", "course-catalogue")
    for path, name in (("/health/", "health"), ("/health/ready/", "api-health")):
        content_type, body = fetch(api + path)
        if content_type != "application/json":
            raise ValueError("Expected JSON health response")
        health = json.loads(body)
        if health.get("status") not in ("ok", "ready"):
            raise ValueError("Health probe failed")
        if name == "api-health":
            version = health.get("version", {})
            if version.get("git_sha") != expected_sha or version.get("image_tag") != expected_sha:
                raise ValueError("API health returned a different release")
        passed(name)

    seen = set()
    kinds = set()
    for kind, path in home.assets:
        url = urljoin(base + "/", path)
        parts = urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" != base or parts.query or parts.fragment:
            continue
        if not parts.path.startswith(("/assets/", "/_next/static/")):
            continue
        if not re.fullmatch(r"/[a-zA-Z0-9_./-]+", parts.path) or ".." in parts.path.split("/"):
            continue
        if url in seen:
            continue
        if len(seen) == 12:
            break
        content_type, body = fetch(url)
        allowed = {
            "script": {"text/javascript", "application/javascript"},
            "style": {"text/css"},
        }
        if content_type not in allowed[kind] or not body.strip() or body.lstrip().startswith(b"<"):
            raise ValueError("Static asset missing, empty or served as an error page")
        kinds.add(kind)
        seen.add(url)
    if kinds != {"script", "style"}:
        raise ValueError("No verified local JavaScript and CSS assets")
    passed("static-assets")
    return checks
