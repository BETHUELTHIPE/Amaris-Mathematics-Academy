"""Allowlisted, bounded reads of existing platform evidence."""

import json
import os
import re
import time
from functools import lru_cache
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener

from django.conf import settings

from .monitoring_status import NoRedirect

REPOSITORY = "BETHUELTHIPE/Amaris-Mathematics-Academy"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
QUALITY_WORKFLOW = "quality-release.yml"
BACKUP_WORKFLOW = "genuine-production-public-backup.yml"
EVIDENCE_CACHE_SECONDS = 300
HTTP_TIMEOUT = 2
MAX_RESPONSE_BYTES = 64 * 1024


@lru_cache(maxsize=24)
def _read_json(url: str, time_bucket: int) -> dict | None:
    del time_bucket
    request = Request(
        url,
        headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "Amaris-Trusted-Advisor"},
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=HTTP_TIMEOUT) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) <= MAX_RESPONSE_BYTES:
            value = json.loads(data)
            if isinstance(value, dict):
                return value
    except (URLError, TimeoutError, OSError, ValueError):
        pass
    return None


def frontend_probe() -> str:
    try:
        url = urlsplit(settings.PUBLIC_SITE_URL)
    except ValueError:
        return "unconfigured"
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        return "unconfigured"
    data = _read_json(f"{url.scheme}://{url.netloc}/health/ready", int(time.monotonic() // 30))
    if data and data.get("status") == "ok" and data.get("service") == "amaris-student-frontend":
        return "reachable"
    return "unavailable"


def deployed_sha() -> str | None:
    value = os.getenv("RENDER_GIT_COMMIT") or os.getenv("RELEASE_GIT_SHA") or ""
    return value.lower() if re.fullmatch(r"[a-fA-F0-9]{40}", value) else None


def latest_workflow_run(workflow: str, **filters: str) -> dict | None:
    if workflow not in (QUALITY_WORKFLOW, BACKUP_WORKFLOW):
        raise ValueError("Workflow is outside the advisor's evidence sources.")
    query = urlencode({"per_page": "1", **filters})
    url = f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/{workflow}/runs?{query}"
    payload = _read_json(url, int(time.monotonic() // EVIDENCE_CACHE_SECONDS))
    runs = payload.get("workflow_runs") if payload else None
    return runs[0] if isinstance(runs, list) and runs and isinstance(runs[0], dict) else None


def workflow_url(workflow: str, run: dict | None = None) -> str:
    # Construct links ourselves rather than reflecting provider-supplied URLs.
    run_id = run.get("id") if run else None
    if type(run_id) is int and run_id > 0:
        return f"{REPOSITORY_URL}/actions/runs/{run_id}"
    return f"{REPOSITORY_URL}/actions/workflows/{workflow}"
