#!/usr/bin/env python3
"""Verify real production frontend branch release rules, not just protected=True."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

REPOSITORY = "BETHUELTHIPE/Amaris-Mathematics-Academy"
PRODUCTION_BRANCH = "render-live-current-20260918"
REQUIRED_CHECKS = {
    "Candidate TypeScript, lint, auth, booking, and dependency checks",
    "Production branch ruleset enforcement active",
}


class ProtectionMissing(Exception):
    pass


def check_rulesets(summaries: list[dict], details: dict[int, dict]) -> None:
    branch_ref = f"refs/heads/{PRODUCTION_BRANCH}"
    active = []
    for summary in summaries:
        if summary.get("enforcement") != "active" or summary.get("target") != "branch":
            continue
        detail = details.get(summary.get("id"))
        if not isinstance(detail, dict):
            raise ProtectionMissing("Unable to inspect active branch ruleset")
        conditions = (detail.get("conditions") or {}).get("ref_name") or {}
        if branch_ref not in conditions.get("include", []) or branch_ref in conditions.get("exclude", []):
            continue
        active.append(detail)

    if not active:
        raise ProtectionMissing("No active ruleset explicitly protects production frontend branch")
    if any(item.get("bypass_actors") for item in active):
        raise ProtectionMissing("Production ruleset permits bypass actors")

    rules = [rule for item in active for rule in item.get("rules", [])]
    # Repository administrators may configure zero mandatory human approvals,
    # but the PR workflow, stale-review protections and strict CI must stay on.
    pull_request_rules = [
        rule for rule in rules
        if rule.get("type") == "pull_request"
        and isinstance((rule.get("parameters") or {}).get("required_approving_review_count"), int)
        and (rule.get("parameters") or {}).get("required_approving_review_count", -1) >= 0
        and (rule.get("parameters") or {}).get("dismiss_stale_reviews_on_push") is True
    ]
    if not pull_request_rules:
        raise ProtectionMissing("Require a protected pull-request workflow with stale-review dismissal")

    status = [rule for rule in rules if rule.get("type") == "required_status_checks"]
    strict = [rule for rule in status if (rule.get("parameters") or {}).get("strict_required_status_checks_policy") is True]
    checks = {
        item.get("context")
        for rule in strict
        for item in (rule.get("parameters") or {}).get("required_status_checks", [])
    }
    missing = sorted(REQUIRED_CHECKS - checks)
    if missing:
        raise ProtectionMissing("Required strict production checks absent: " + ", ".join(missing))
    if not any(rule.get("type") == "non_fast_forward" for rule in rules):
        raise ProtectionMissing("Force pushes must be disabled")


def fetch_json(url: str, token: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError) as exc:
        raise ProtectionMissing("Cannot read active GitHub branch rulesets") from exc


def main() -> int:
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        print("BLOCK: Unexpected repository")
        return 1
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("BLOCK: GitHub ruleset-read credential missing")
        return 1
    base = f"https://api.github.com/repos/{REPOSITORY}/rulesets"
    try:
        summaries = fetch_json(base + "?includes_parents=true", token)
        if not isinstance(summaries, list):
            raise ProtectionMissing("Unexpected GitHub ruleset response")
        details = {entry["id"]: fetch_json(base + f"/{entry['id']}", token)
                   for entry in summaries if entry.get("target") == "branch"
                   and entry.get("enforcement") == "active"}
        check_rulesets(summaries, details)
    except ProtectionMissing as exc:
        print("BLOCK:", exc)
        return 1
    print("PASS: Production frontend retains PR workflow, stale-review dismissal, strict CI and no force pushes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
