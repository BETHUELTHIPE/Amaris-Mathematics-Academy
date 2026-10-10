#!/usr/bin/env python3
"""Fail-closed, secret-safe staging backup configuration and snapshot checks.

This verifies READ-ONLY connectivity prerequisites. It does not certify that a
real staging restore has succeeded; the isolated restore workflow tests that
separate step using synthetic data.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit


class ReadinessError(ValueError):
    pass


def validate_configuration(env):
    required = (
        "STAGING_BACKUP_DATABASE_URL",
        "STAGING_BACKUP_EXPECTED_DB_HOST",
        "STAGING_BACKUP_EXPECTED_DB_NAME",
        "RESTIC_REPOSITORY",
        "RESTIC_PASSWORD",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    )
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        # Variable NAMES only, never credentials or URLs.
        raise ReadinessError("Missing staging settings: " + ", ".join(missing))
    try:
        parsed = urlsplit(env["STAGING_BACKUP_DATABASE_URL"])
        hostname = parsed.hostname
        database = unquote(PurePosixPath(parsed.path).name)
        port = parsed.port
    except ValueError as exc:
        raise ReadinessError("Invalid staging PostgreSQL URL") from exc
    if parsed.scheme not in ("postgres", "postgresql") or not hostname or not database:
        raise ReadinessError("Invalid staging PostgreSQL URL")
    if not port and not parsed.path:
        raise ReadinessError("Invalid staging PostgreSQL URL")
    if hostname.lower() != env["STAGING_BACKUP_EXPECTED_DB_HOST"].strip().lower():
        raise ReadinessError("Staging database host does not match the pinned identity")
    if database != env["STAGING_BACKUP_EXPECTED_DB_NAME"].strip():
        raise ReadinessError("Staging database name does not match the pinned identity")
    if "prod" in database.lower() or "prod" in hostname.lower():
        raise ReadinessError("Refusing a staging check against a production-labelled database")
    if not env["RESTIC_REPOSITORY"].startswith(("s3:", "sftp:", "rest:", "b2:", "azure:", "gs:", "rclone:")):
        raise ReadinessError("Staging restic repository must use durable remote storage")
    try:
        max_age = int(env.get("STAGING_BACKUP_MAX_AGE_HOURS", "48"))
    except ValueError as exc:
        raise ReadinessError("Invalid staging snapshot age limit") from exc
    if not 1 <= max_age <= 168:
        raise ReadinessError("Staging snapshot age must be between 1 and 168 hours")
    return max_age


def verify_recent_snapshot(snapshots, max_age_hours, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)
    if not isinstance(snapshots, list):
        raise ReadinessError("Invalid restic snapshot response")
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        tags = snapshot.get("tags", [])
        if not isinstance(tags, list) or not {"automated", "amaris"}.issubset(set(tags)):
            continue
        try:
            taken = datetime.fromisoformat(snapshot["time"].replace("Z", "+00:00"))
        except (ValueError, KeyError, AttributeError):
            continue
        if taken.tzinfo is not None and cutoff <= taken <= now + timedelta(minutes=5):
            return
    raise ReadinessError("No sufficiently recent tagged staging backup snapshot")


def main():
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("config", "snapshots"):
            raise ReadinessError("Usage: check_staging_backup_readiness.py config|snapshots")
        age = validate_configuration(os.environ)
        if sys.argv[1] == "snapshots":
            verify_recent_snapshot(json.load(sys.stdin), age)
        print("Staging backup " + sys.argv[1] + " verification PASS")
    except (ReadinessError, json.JSONDecodeError) as exc:
        print("Staging backup verification failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
