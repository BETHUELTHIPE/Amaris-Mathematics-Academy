#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REQUIRED_IDS = set(range(1, 21))


def validate_manifest(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["acceptance manifest must be a JSON object"]

    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        return ["criteria must be a JSON array"]

    entries: dict[int, dict] = {}
    for index, value in enumerate(criteria):
        if not isinstance(value, dict) or not isinstance(value.get("id"), int):
            errors.append(f"criterion at position {index + 1} has no integer id")
            continue
        criterion_id = value["id"]
        if criterion_id in entries:
            errors.append(f"criterion {criterion_id} is duplicated")
        entries[criterion_id] = value

    for criterion_id in sorted(REQUIRED_IDS - entries.keys()):
        errors.append(f"criterion {criterion_id} is missing")
    for criterion_id in sorted(entries.keys() - REQUIRED_IDS):
        errors.append(f"unexpected criterion {criterion_id}")

    for criterion_id in sorted(REQUIRED_IDS & entries.keys()):
        item = entries[criterion_id]
        if item.get("status") != "passed":
            errors.append(f"criterion {criterion_id} is not passed")
        evidence = item.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(isinstance(value, str) and value.strip() for value in evidence)
        ):
            errors.append(f"criterion {criterion_id} has no evidence")
        if (
            not isinstance(item.get("verified_by"), str)
            or not item["verified_by"].strip()
        ):
            errors.append(f"criterion {criterion_id} has no verifier")
        verified_at = item.get("verified_at")
        if not isinstance(verified_at, str):
            errors.append(f"criterion {criterion_id} has no verification timestamp")
        else:
            try:
                datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
            except ValueError:
                errors.append(
                    f"criterion {criterion_id} has an invalid verification timestamp"
                )

    if data.get("release_status") != "accepted":
        errors.append("release_status must be accepted")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Block production until all Amaris acceptance evidence is approved."
    )
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Acceptance gate could not read the manifest: {exc}", file=sys.stderr)
        return 2

    errors = validate_manifest(data)
    if errors:
        print("Production acceptance is blocked:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("All 20 production acceptance criteria have approved evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
