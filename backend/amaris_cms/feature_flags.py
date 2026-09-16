from __future__ import annotations

import os


def enabled(name: str, *, default: bool = False) -> bool:
    """Return whether a named feature flag is enabled.

    Flags are comma-separated in AMARIS_FEATURE_FLAGS. Risky features should be
    disabled by default and explicitly enabled after staging acceptance.
    """

    configured = {
        value.strip().lower()
        for value in os.getenv("AMARIS_FEATURE_FLAGS", "").split(",")
        if value.strip()
    }
    normalized = name.strip().lower()
    if normalized in configured:
        return True
    return default
