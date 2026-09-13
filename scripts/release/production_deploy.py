#!/usr/bin/env python3
"""One production transaction; every failure after deploy attempts verified recovery.

The hosting adapter owns an exclusive lease and a watchdog so runner loss cannot
leave an uncommitted release live. See docs/PRODUCTION_DEPLOYMENT.md for API v2.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

IMAGE_REPOSITORY = "docker.io/bethuelm/amaris-mathematics-academy"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(image, sha, digest):
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "Invalid full Git SHA")
    require(image == f"{IMAGE_REPOSITORY}:{sha}", "Image repository/tag must match the exact release SHA")
    require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", digest)), "Missing immutable registry digest")
    return {"image": image, "git_sha": sha, "digest": digest}


def https(url):
    parts = urlsplit(url)
    require(
        parts.scheme == "https" and parts.hostname and not parts.username and not parts.password and not parts.fragment,
        "Deployment endpoints must be HTTPS URLs without credentials or fragments",
    )
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Deployment request redirects are forbidden")


def request_json(url, payload=None, token=None, key=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if key:
        headers["Idempotency-Key"] = key
    body = None if payload is None else json.dumps(payload).encode()
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(https(url), data=body, headers=headers)
    # No automatic mutation retries: the adapter reconciles an ambiguous request
    # by transaction ID and serializes rollback against any in-flight operation.
    with build_opener(NoRedirect).open(request, timeout=120 if body else 10) as response:
        return json.load(response)


class Adapter:
    def __init__(self, env):
        self.env = env
        self.transaction = f"{env['GITHUB_RUN_ID']}-{env['GITHUB_RUN_ATTEMPT']}"
        for name in ("DEPLOY_WEBHOOK_URL", "BACKUP_WEBHOOK_URL", "HEALTHCHECK_URL", "PRODUCTION_URL"):
            https(env[name])
        for name in ("DEPLOY_TOKEN", "BACKUP_TOKEN", "PRODUCTION_STUDENT_EMAIL", "PRODUCTION_STUDENT_PASSWORD"):
            require(bool(env.get(name)), f"{name} is required")
        require(
            bool(re.fullmatch(r"/courses/[a-z0-9-]+", env.get("PRODUCTION_COURSE_PATH", ""))),
            "A real course path is required",
        )
        lesson = env.get("PRODUCTION_LESSON_PATH", "")
        require(
            bool(re.fullmatch(r"/[a-zA-Z0-9/_-]+", lesson))
            and lesson not in (env["PRODUCTION_COURSE_PATH"], "/dashboard", "/login", "/register"),
            "A protected lesson fixture is required",
        )

    def call(self, action, release=None, **extra):
        payload = {
            "contract_version": 2,
            "action": action,
            "environment": "production",
            "transaction_id": self.transaction,
            **extra,
        }
        if release:
            payload.update(release)
            payload["image_reference"] = f"{release['image']}@{release['digest']}"
        backup = action == "backup"
        return request_json(
            self.env["BACKUP_WEBHOOK_URL" if backup else "DEPLOY_WEBHOOK_URL"],
            payload,
            self.env["BACKUP_TOKEN" if backup else "DEPLOY_TOKEN"],
            f"{self.transaction}:{action}",
        )

    def health(self, release):
        body = request_json(self.env["HEALTHCHECK_URL"])
        require(body.get("status") in ("ok", "ready"), "Readiness failed")
        version = body.get("version", {})
        require(
            version.get("git_sha") == release["git_sha"] and version.get("image_tag") == release["git_sha"],
            "Readiness returned a different release",
        )

    def journey(self):
        # The browser child receives only the synthetic account, never deploy or
        # backup tokens. It suppresses page contents, cookies, traces and secrets.
        allowed = {
            "PATH",
            "HOME",
            "TMPDIR",
            "CHROME_PATH",
            "PRODUCTION_URL",
            "PRODUCTION_COURSE_PATH",
            "PRODUCTION_LESSON_PATH",
            "PRODUCTION_STUDENT_EMAIL",
            "PRODUCTION_STUDENT_PASSWORD",
        }
        env = {k: v for k, v in self.env.items() if k in allowed}
        subprocess.run(["node", "scripts/release/production-journey.mjs"], env=env, check=True, timeout=150)


class Deployment:
    def __init__(self, adapter, candidate, record_path, migration_risk="high", sleep=time.sleep):
        require(migration_risk in ("low", "high"), "Invalid migration risk")
        self.adapter = adapter
        self.candidate = candidate
        self.previous = None
        self.changed = False
        self.leased = False
        self.sleep = sleep
        self.risk = migration_risk
        self.path = Path(record_path)
        self.record = {
            "environment": "production",
            "candidate": candidate,
            "transaction_id": adapter.transaction,
            "events": [],
        }

    def event(self, phase, status="passed"):
        self.record["events"].append({"phase": phase, "status": status, "at": datetime.now(UTC).isoformat()})
        self.path.write_text(json.dumps(self.record, indent=2) + "\n")
        print(f"Production: {phase}: {status}", flush=True)

    def completed(self, action, release=None, **extra):
        response = self.adapter.call(action, release, **extra)
        require(response.get("status") == "completed", f"{action} has not completed")
        require(
            response.get("transaction_id") == self.adapter.transaction, f"{action} belongs to a different transaction"
        )
        if release:
            require(response.get("release") == release, f"{action} returned a different release")
        return response

    def verify(self, release, attempts=12):
        for attempt in range(attempts):
            try:
                state = self.adapter.call("status")
                require(state.get("active") == release, "Hosting state differs from requested release")
                self.adapter.health(release)
                return
            except Exception:
                if attempt == attempts - 1:
                    raise
                self.sleep(5)

    def execute(self):
        phase = "preflight"
        try:
            self.event("started")
            preflight = self.completed("preflight", self.candidate, migration_risk=self.risk)
            for field in ("registry_verified", "ready", "rollback_compatible", "watchdog_ready"):
                require(preflight.get(field) is True, f"Preflight did not prove {field}")
            self.event("image-and-readiness")
            phase = "acquire-lock"
            lease = self.completed("acquire", self.candidate, watchdog_seconds=1200)
            self.leased = True
            previous = lease["previous"]
            self.previous = identity(previous["image"], previous["git_sha"], previous["digest"])
            require(lease.get("watchdog_armed") is True, "Hosting rollback watchdog is not armed")
            self.record["previous"] = self.previous
            self.verify(self.previous)
            self.event("previous-release-healthy")
            phase = "backup"
            backup = self.completed("backup", self.candidate, tag="pre-deployment")
            require(
                backup.get("verified") is True
                and isinstance(backup.get("recovery_id"), str)
                and bool(backup["recovery_id"].strip()),
                "No verified recovery point",
            )
            self.record["recovery_id"] = backup["recovery_id"]
            self.event("backup")
            phase = "migration-plan"
            plan = self.completed("migration-plan", self.candidate)
            require(
                plan.get("backwards_compatible") is True and plan.get("destructive") is False,
                "Unsafe migration plan; use a separately reviewed maintenance procedure",
            )
            self.event("migration-plan")
            phase = "deploy"
            # Arm recovery BEFORE the request; a failed response can mean the
            # server changed state but its acknowledgement was lost.
            self.changed = True
            self.completed("deploy", self.candidate, previous=self.previous, recovery_id=backup["recovery_id"])
            self.event("deploy")
            phase = "migrate"
            migration = self.completed(
                "migrate", self.candidate, recovery_id=backup["recovery_id"], backwards_compatible_only=True
            )
            require(
                migration.get("pending") == 0 and migration.get("backwards_compatible") is True,
                "Migrations are incomplete or incompatible with rollback",
            )
            self.event("migrate")
            phase = "health"
            self.verify(self.candidate)
            self.event("health")
            phase = "student-journey"
            self.adapter.journey()
            self.event("smoke-and-student-journey")
            phase = "monitor"
            # Ten samples over five minutes; no variable can disable production monitoring.
            for _ in range(10):
                self.sleep(30)
                self.verify(self.candidate, attempts=1)
                monitor = self.completed("monitor", self.candidate)
                require(
                    monitor.get("healthy") is True and monitor.get("critical_alerts") == 0,
                    "Critical production telemetry failed",
                )
            self.event("monitor-five-minutes")
            phase = "commit"
            self.completed("commit", self.candidate)
            self.changed = False
            self.leased = False  # Commit releases the hosting lease and disarms its watchdog.
            self.record["outcome"] = "deployed"
            self.event("committed")
            return 0
        except BaseException as error:
            # Do not record exception text: remote payloads can contain secrets.
            self.record["failed_phase"] = phase
            self.record["error_type"] = type(error).__name__
            if self.changed:
                # Reserve recovery for cancellation too; hosting watchdog remains
                # authoritative if the runner is killed before recovery completes.
                for sig in (signal.SIGINT, signal.SIGTERM):
                    signal.signal(sig, signal.SIG_IGN)
                try:
                    self.completed("rollback", self.previous)
                    self.verify(self.previous)
                    self.adapter.journey()
                    self.record["restored"] = self.previous
                    self.record["outcome"] = "rolled_back"
                    self.event("rollback-verified")
                except BaseException:
                    self.record["outcome"] = "rollback_failed"
                    self.event("rollback", "critical-failure")
                    # Keep the adapter watchdog armed and the environment locked.
                    print(
                        "::error::CRITICAL: rollback could not be verified; "
                        "hosting recovery and operator intervention required."
                    )
                    return 2
            else:
                self.record["outcome"] = "blocked"
                self.event(phase, "blocked")
            if self.leased:
                try:
                    self.completed("abort")
                    self.leased = False
                except Exception:
                    self.event("lease-release", "failed-watchdog-retained")
            return 1


def main():
    candidate = identity(os.environ["RELEASE_IMAGE"], os.environ["GITHUB_SHA"], os.environ["RELEASE_DIGEST"])
    deployment = Deployment(
        Adapter(os.environ),
        candidate,
        os.environ.get("DEPLOYMENT_RECORD_PATH", "production-deployment-record.json"),
        os.environ["MIGRATION_RISK"],
    )

    def interrupted(_signum, _frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    result = deployment.execute()
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as output:
            output.write(
                f"\n## Production deployment\n\n- Git SHA: `{candidate['git_sha']}`\n"
                f"- Image: `{candidate['image']}@{candidate['digest']}`\n"
                f"- Outcome: **{deployment.record['outcome']}**\n"
            )
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("Production configuration or evidence recording failed; inspect the deployment record.", file=sys.stderr)
        raise SystemExit(1) from None
