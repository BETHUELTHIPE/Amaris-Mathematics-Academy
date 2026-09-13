#!/usr/bin/env python3
"""Fail closed if native protection or approval of this run is missing."""

import json
import os
import sys
from urllib.request import Request, urlopen


def validate(environment, policies, reviews, run, sha):
    if environment.get("name") != "production":
        raise ValueError("The production environment is missing")
    rules = environment.get("protection_rules", [])
    if not any(r.get("type") == "required_reviewers" and r.get("reviewers") for r in rules):
        raise ValueError("Production must have native required reviewers")
    branch_policy = environment.get("deployment_branch_policy") or {}
    if not branch_policy.get("custom_branch_policies"):
        raise ValueError("Production requires selected deployment branches")
    branches = policies.get("branch_policies", [])
    if policies.get("total_count", len(branches)) != len(branches):
        raise ValueError("Could not verify every deployment branch policy")
    if not branches or any(p.get("name") != "main" or p.get("type") != "branch" for p in branches):
        raise ValueError("Only the main branch may deploy; tags and wildcards are forbidden")
    if run.get("head_sha") != sha or run.get("head_branch") != "main":
        raise ValueError("Approval must belong to the exact main release run")
    approvals = [
        r
        for r in reviews
        if r.get("state") == "approved" and any(e.get("id") == environment.get("id") for e in r.get("environments", []))
    ]
    if not approvals:
        raise ValueError("No explicit production approval exists for this workflow run")
    return approvals


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("Production only accepts the main branch")
    repo = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    token = os.environ["GH_TOKEN"]

    def get(path):
        request = Request(
            f"https://api.github.com/repos/{repo}/{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    approvals = validate(
        get("environments/production"),
        get("environments/production/deployment-branch-policies?per_page=100"),
        get(f"actions/runs/{run_id}/approvals"),
        get(f"actions/runs/{run_id}"),
        os.environ["GITHUB_SHA"],
    )
    # Review bodies are deliberately excluded from logs and evidence.
    evidence = {
        "run_id": run_id,
        "git_sha": os.environ["GITHUB_SHA"],
        "approvers": [r.get("user", {}).get("login") for r in approvals],
    }
    print("Native production protection and explicit approval verified.")
    with open("production-approval-record.json", "w") as output:
        json.dump(evidence, output, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Production approval verification failed. Check environment reviewers, "
            "main-only branches, API access, and this run's approval history.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
