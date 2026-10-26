#!/usr/bin/env python3
"""Fail-closed production approval gate, independent from successful staging CI.

A human must explicitly approve the *exact* release SHA in the protected
GitHub production environment. The release workflow reads only environment
variables, never creates an approval itself.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

REPO = "BETHUELTHIPE/Amaris-Mathematics-Academy"
SHA = re.compile(r"^[0-9a-f]{40}$")
RUN_ID = re.compile(r"^[1-9][0-9]{0,18}$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{11,159}$")


class ReleaseBlocked(Exception):
    """A production release requirement has not been independently satisfied."""


def validate_release(
    settings: Mapping[str, str],
    fetch_run: Callable[[int], dict],
) -> dict[str, str]:
    """Return pinning evidence only; no changes to GitHub or Render."""
    if settings.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise ReleaseBlocked("A staging push or green CI run cannot authorize production")
    if settings.get("GITHUB_REPOSITORY") != REPO:
        raise ReleaseBlocked("Repository does not match the authorized Amaris source")
    if settings.get("GITHUB_REF") != "refs/heads/main":
        raise ReleaseBlocked("Production release must be dispatched from protected main")

    release_sha = settings.get("GITHUB_SHA", "").strip().lower()
    approved_sha = settings.get("PRODUCTION_APPROVED_SHA", "").strip().lower()
    rollback_sha = settings.get("PRODUCTION_ROLLBACK_SHA", "").strip().lower()
    if not SHA.fullmatch(release_sha) or approved_sha != release_sha:
        raise ReleaseBlocked("Exact current commit has not been separately approved")
    if not SHA.fullmatch(rollback_sha) or rollback_sha == release_sha:
        raise ReleaseBlocked("Record a distinct validated rollback commit")

    supplied = settings.get("PRODUCTION_APPROVAL_INPUT", "").strip()
    authorized = settings.get("PRODUCTION_APPROVAL_REFERENCE", "").strip()
    if not REF.fullmatch(supplied) or supplied != authorized:
        raise ReleaseBlocked("Owner's separate per-release approval reference is absent or mismatched")

    evidence = {}
    for key in ("STAGING", "BACKUP"):
        raw = settings.get("PRODUCTION_" + key + "_RUN_ID", "").strip()
        if not RUN_ID.fullmatch(raw):
            raise ReleaseBlocked(f"Missing exact-sha {key.lower()} GitHub Actions evidence")
        evidence[key] = int(raw)
    if evidence["STAGING"] == evidence["BACKUP"]:
        raise ReleaseBlocked("Staging and backup need distinct verified workflow runs")

    for name, run_id in evidence.items():
        run = fetch_run(run_id)
        if not isinstance(run, dict):
            raise ReleaseBlocked(f"{name.lower()} workflow run is inaccessible")
        if (
            run.get("id") != run_id
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("head_sha", "").lower() != release_sha
            or (run.get("repository") or {}).get("full_name") != REPO
        ):
            raise ReleaseBlocked(f"{name.lower()} evidence is failed, stale or for another commit")
        if name == "BACKUP" and run.get("event") != "workflow_dispatch":
            raise ReleaseBlocked("Production backup must be explicitly triggered and verified")
        # Reject a wrong workflow supplied as the evidence ID.
        path = (run.get("path") or "").split("@", 1)[0]
        if name == "STAGING" and not path.endswith("/staging-acceptance.yml"):
            raise ReleaseBlocked("Staging evidence does not identify the designated acceptance workflow")
        if name == "BACKUP" and not path.endswith("/genuine-production-public-backup.yml"):
            raise ReleaseBlocked("Backup evidence is not the genuine protected backup workflow")

    return {
        "approved_sha": release_sha,
        "rollback_sha": rollback_sha,
        "staging_run_id": str(evidence["STAGING"]),
        "backup_run_id": str(evidence["BACKUP"]),
    }


def github_run(run_id: int, token: str) -> dict:
    url = f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Amaris-release-audit",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ReleaseBlocked("Cannot independently retrieve protected workflow evidence") from exc


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("BLOCK: Missing GitHub Actions read-only access for independent release evidence")
        return 1
    try:
        approved = validate_release(os.environ, lambda run: github_run(run, token))
    except ReleaseBlocked as exc:
        print("BLOCK:", exc)
        return 1
    print("PASS: Exact commit approved via separate protected production environment variables")
    print("PASS: Staging and backup are successfully completed for precisely that SHA")
    print("PASS: Distinct rollback SHA recorded; workflow remains manual and environment-protected")
    print("Approved release SHA:", approved["approved_sha"])
    print("Staging run:", approved["staging_run_id"])
    print("Backup run:", approved["backup_run_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
